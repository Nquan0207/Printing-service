package store

import (
	"context"
	"errors"
	"fmt"
	"strconv"
	"strings"

	"github.com/jackc/pgx/v5"
)

var ErrNotFound = errors.New("not found")

// maxCatalogRows bounds the rows pulled before grouping happens in Go. The
// crawled catalog is ~70 products, so this never bites; it exists so an
// unfiltered query can never stream an unbounded result set.
const maxCatalogRows = 500

type Category struct {
	ID   int64
	Slug string
	Name string
	// ProductCount counts active products; lets a caller build category chips
	// without fetching the whole catalog.
	ProductCount int
}

type Size struct {
	ID                 int64
	Name               string
	PriceAdjustmentJPY int
}

type Product struct {
	ID              int64
	SourceProductID *string
	Name            string
	Brand           *string
	Description     *string
	BasePriceJPY    int
	Category        Category
	Sizes           []Size
	ImageKeys       []string
}

// ProductFilter mirrors the query parameters of GET /api/v1/products.
type ProductFilter struct {
	Query string
	// CategorySlugs matches any of the given slugs. Empty means every category.
	CategorySlugs []string
	MinPriceJPY   *int
	MaxPriceJPY   *int
	// IncludeInactive is set only by admin views; the shop never sees
	// deactivated products.
	IncludeInactive bool
}

// Categories returns only categories that hold at least one active product,
// so a filter chip never renders a dead option.
func (s *Store) Categories(ctx context.Context) ([]Category, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT c.id, c.slug, c.name,
		       (SELECT COUNT(*) FROM products p
		         WHERE p.category_id = c.id AND p.is_active)::int
		FROM categories c
		WHERE EXISTS (
			SELECT 1 FROM products p
			WHERE p.category_id = c.id AND p.is_active
		)
		ORDER BY c.name`)
	if err != nil {
		return nil, fmt.Errorf("query categories: %w", err)
	}
	defer rows.Close()

	var out []Category
	for rows.Next() {
		var c Category
		if err := rows.Scan(&c.ID, &c.Slug, &c.Name, &c.ProductCount); err != nil {
			return nil, fmt.Errorf("scan category: %w", err)
		}
		out = append(out, c)
	}
	return out, rows.Err()
}

// SearchProducts returns active products matching the filter, ordered by id,
// each with its sizes and image keys loaded.
func (s *Store) SearchProducts(ctx context.Context, f ProductFilter) ([]Product, error) {
	where := []string{}
	args := []any{}
	if !f.IncludeInactive {
		where = append(where, "p.is_active")
	}

	add := func(clause string, value any) {
		args = append(args, value)
		where = append(where, strings.ReplaceAll(clause, "?", "$"+strconv.Itoa(len(args))))
	}

	if q := strings.TrimSpace(f.Query); q != "" {
		add("(p.name ILIKE '%' || ? || '%' OR p.description ILIKE '%' || ? || '%')", q)
	}
	if len(f.CategorySlugs) > 0 {
		// ANY($n) keeps this one placeholder regardless of how many slugs are
		// requested, so the statement still plans and caches predictably.
		add("c.slug = ANY(?)", f.CategorySlugs)
	}
	// A product matches on price when *some single size* falls inside the
	// bounds -- both conditions in one EXISTS, not two. Split across separate
	// EXISTS clauses, an S under max and an L over min would wrongly match.
	if f.MinPriceJPY != nil || f.MaxPriceJPY != nil {
		price := []string{"ps.product_id = p.id"}
		if f.MinPriceJPY != nil {
			args = append(args, *f.MinPriceJPY)
			price = append(price, "p.base_price_jpy + ps.price_adjustment_jpy >= $"+strconv.Itoa(len(args)))
		}
		if f.MaxPriceJPY != nil {
			args = append(args, *f.MaxPriceJPY)
			price = append(price, "p.base_price_jpy + ps.price_adjustment_jpy <= $"+strconv.Itoa(len(args)))
		}
		where = append(where, "EXISTS (SELECT 1 FROM product_sizes ps WHERE "+
			strings.Join(price, " AND ")+")")
	}

	sql := `
		SELECT p.id, p.source_product_id, p.name, p.brand, p.description,
		       p.base_price_jpy, c.id, c.slug, c.name
		FROM products p
		JOIN categories c ON c.id = p.category_id
		WHERE ` + joinWhere(where) + `
		ORDER BY p.id
		LIMIT ` + strconv.Itoa(maxCatalogRows)

	rows, err := s.pool.Query(ctx, sql, args...)
	if err != nil {
		return nil, fmt.Errorf("query products: %w", err)
	}
	products, err := scanProducts(rows)
	if err != nil {
		return nil, err
	}
	return products, s.attachSizesAndImages(ctx, products)
}

// Product returns one product by id, including its description.
func (s *Store) Product(ctx context.Context, id int64) (*Product, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT p.id, p.source_product_id, p.name, p.brand, p.description,
		       p.base_price_jpy, c.id, c.slug, c.name
		FROM products p
		JOIN categories c ON c.id = p.category_id
		WHERE p.id = $1 AND p.is_active`, id)
	if err != nil {
		return nil, fmt.Errorf("query product: %w", err)
	}
	products, err := scanProducts(rows)
	if err != nil {
		return nil, err
	}
	if len(products) == 0 {
		return nil, ErrNotFound
	}
	if err := s.attachSizesAndImages(ctx, products); err != nil {
		return nil, err
	}
	return &products[0], nil
}

func scanProducts(rows pgx.Rows) ([]Product, error) {
	defer rows.Close()
	var out []Product
	for rows.Next() {
		var p Product
		if err := rows.Scan(
			&p.ID, &p.SourceProductID, &p.Name, &p.Brand, &p.Description,
			&p.BasePriceJPY, &p.Category.ID, &p.Category.Slug, &p.Category.Name,
		); err != nil {
			return nil, fmt.Errorf("scan product: %w", err)
		}
		out = append(out, p)
	}
	return out, rows.Err()
}

// attachSizesAndImages loads children for every product in two queries rather
// than one per product.
func (s *Store) attachSizesAndImages(ctx context.Context, products []Product) error {
	if len(products) == 0 {
		return nil
	}
	ids := make([]int64, len(products))
	index := make(map[int64]*Product, len(products))
	for i := range products {
		ids[i] = products[i].ID
		index[products[i].ID] = &products[i]
	}

	// Sizes ascend by price so they read S, M, L. Ordering by size_name would
	// give L, M, S -- alphabetical, and wrong.
	sizeRows, err := s.pool.Query(ctx, `
		SELECT product_id, id, size_name, price_adjustment_jpy
		FROM product_sizes
		WHERE product_id = ANY($1)
		ORDER BY product_id, price_adjustment_jpy`, ids)
	if err != nil {
		return fmt.Errorf("query sizes: %w", err)
	}
	defer sizeRows.Close()
	for sizeRows.Next() {
		var productID int64
		var sz Size
		if err := sizeRows.Scan(&productID, &sz.ID, &sz.Name, &sz.PriceAdjustmentJPY); err != nil {
			return fmt.Errorf("scan size: %w", err)
		}
		if p := index[productID]; p != nil {
			p.Sizes = append(p.Sizes, sz)
		}
	}
	if err := sizeRows.Err(); err != nil {
		return err
	}

	// Insertion order; the first image is the card thumbnail.
	imageRows, err := s.pool.Query(ctx, `
		SELECT product_id, image_key
		FROM product_images
		WHERE product_id = ANY($1)
		ORDER BY product_id, id`, ids)
	if err != nil {
		return fmt.Errorf("query images: %w", err)
	}
	defer imageRows.Close()
	for imageRows.Next() {
		var productID int64
		var key string
		if err := imageRows.Scan(&productID, &key); err != nil {
			return fmt.Errorf("scan image: %w", err)
		}
		if p := index[productID]; p != nil {
			p.ImageKeys = append(p.ImageKeys, key)
		}
	}
	return imageRows.Err()
}

// joinWhere keeps the SQL valid when every filter is optional.
func joinWhere(clauses []string) string {
	if len(clauses) == 0 {
		return "TRUE"
	}
	return strings.Join(clauses, " AND ")
}
