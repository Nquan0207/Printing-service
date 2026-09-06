package httpapi

import (
	"errors"
	"net/http"
	"net/url"
	"sort"
	"strconv"
	"strings"

	"github.com/octguy/stockroom/internal/store"
)

const (
	defaultLimit = 20
	maxLimit     = 100
	maxPerGroup  = 50
)

type categoryJSON struct {
	ID   int64  `json:"id"`
	Slug string `json:"slug"`
	Name string `json:"name"`
	// Omitted when nested inside a product, where it would be noise.
	ProductCount int `json:"product_count,omitempty"`
}

type sizeJSON struct {
	ID                 int64  `json:"id"`
	SizeName           string `json:"size_name"`
	PriceAdjustmentJPY int    `json:"price_adjustment_jpy"`
	UnitPriceJPY       int    `json:"unit_price_jpy"`
}

type productJSON struct {
	ID              int64        `json:"id"`
	SourceProductID *string      `json:"source_product_id,omitempty"`
	Name            string       `json:"name"`
	Brand           *string      `json:"brand"`
	Description     *string      `json:"description,omitempty"`
	Category        categoryJSON `json:"category"`
	BasePriceJPY    int          `json:"base_price_jpy"`
	Sizes           []sizeJSON   `json:"sizes"`
	Images          []string     `json:"images"`
}

type groupJSON struct {
	Category categoryJSON  `json:"category"`
	Count    int           `json:"count"`
	Products []productJSON `json:"products"`
}

type productListJSON struct {
	Groups []groupJSON `json:"groups"`
	Count  int         `json:"count"`
}

func toCategory(c store.Category) categoryJSON {
	return categoryJSON{ID: c.ID, Slug: c.Slug, Name: c.Name}
}

// toProduct precomputes unit prices and rewrites image keys as same-origin
// /media paths: a View must never do arithmetic or build a URL.
func toProduct(p store.Product, withDescription bool) productJSON {
	sizes := make([]sizeJSON, 0, len(p.Sizes))
	for _, s := range p.Sizes {
		sizes = append(sizes, sizeJSON{
			ID:                 s.ID,
			SizeName:           s.Name,
			PriceAdjustmentJPY: s.PriceAdjustmentJPY,
			UnitPriceJPY:       p.BasePriceJPY + s.PriceAdjustmentJPY,
		})
	}
	images := make([]string, 0, len(p.ImageKeys))
	for _, key := range p.ImageKeys {
		images = append(images, "/media/"+key)
	}
	out := productJSON{
		ID:              p.ID,
		SourceProductID: p.SourceProductID,
		Name:            p.Name,
		Brand:           p.Brand,
		Category:        toCategory(p.Category),
		BasePriceJPY:    p.BasePriceJPY,
		Sizes:           sizes,
		Images:          images,
	}
	if withDescription {
		out.Description = p.Description
	}
	return out
}

func (s *Server) ListCategories(w http.ResponseWriter, r *http.Request) {
	categories, err := s.store.Categories(r.Context())
	if err != nil {
		writeInternal(w, "list categories", err)
		return
	}
	out := make([]categoryJSON, 0, len(categories))
	for _, c := range categories {
		entry := toCategory(c)
		entry.ProductCount = c.ProductCount
		out = append(out, entry)
	}
	writeJSON(w, http.StatusOK, map[string]any{"categories": out})
}

// categoryParams collects the requested category slugs.
//
// Accepts a repeated parameter (?category=a&category=b), a comma-separated
// value (?category=a,b), or the plural spelling — callers reach for all three,
// and rejecting two of them is a papercut with no upside.
func categoryParams(q url.Values) []string {
	seen := map[string]bool{}
	out := []string{}
	for _, key := range []string{"category", "categories"} {
		for _, raw := range q[key] {
			for _, part := range strings.Split(raw, ",") {
				part = strings.TrimSpace(part)
				if part != "" && !seen[part] {
					seen[part] = true
					out = append(out, part)
				}
			}
		}
	}
	return out
}

func (s *Server) SearchProducts(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()

	limit, err := intParam(q.Get("limit"), defaultLimit, 1, maxLimit)
	if err != nil {
		writeError(w, http.StatusBadRequest, CodeInvalidRequest, "limit must be between 1 and 100.")
		return
	}
	perGroup, err := intParam(q.Get("per_category"), 0, 1, maxPerGroup)
	if err != nil {
		writeError(w, http.StatusBadRequest, CodeInvalidRequest, "per_category must be between 1 and 50.")
		return
	}
	minPrice, err := optionalInt(q.Get("min_price"))
	if err != nil {
		writeError(w, http.StatusBadRequest, CodeInvalidRequest, "min_price must be a non-negative integer.")
		return
	}
	maxPrice, err := optionalInt(q.Get("max_price"))
	if err != nil {
		writeError(w, http.StatusBadRequest, CodeInvalidRequest, "max_price must be a non-negative integer.")
		return
	}

	products, err := s.store.SearchProducts(r.Context(), store.ProductFilter{
		Query:         strings.TrimSpace(q.Get("q")),
		CategorySlugs: categoryParams(q),
		MinPriceJPY:   minPrice,
		MaxPriceJPY:   maxPrice,
	})
	if err != nil {
		writeInternal(w, "search products", err)
		return
	}
	writeJSON(w, http.StatusOK, groupByCategory(products, limit, perGroup))
}

// groupByCategory builds the rendered sections: groups ordered by product
// count descending then category name, products by id. Empty groups are never
// emitted -- a section header with nothing under it is a UI bug.
func groupByCategory(products []store.Product, limit, perGroup int) productListJSON {
	order := []int64{}
	byCategory := map[int64]*groupJSON{}
	for _, p := range products {
		g, ok := byCategory[p.Category.ID]
		if !ok {
			g = &groupJSON{Category: toCategory(p.Category), Products: []productJSON{}}
			byCategory[p.Category.ID] = g
			order = append(order, p.Category.ID)
		}
		if perGroup > 0 && len(g.Products) >= perGroup {
			continue
		}
		g.Products = append(g.Products, toProduct(p, false))
	}

	groups := make([]groupJSON, 0, len(order))
	for _, id := range order {
		if g := byCategory[id]; len(g.Products) > 0 {
			groups = append(groups, *g)
		}
	}
	sort.SliceStable(groups, func(i, j int) bool {
		if len(groups[i].Products) != len(groups[j].Products) {
			return len(groups[i].Products) > len(groups[j].Products)
		}
		return groups[i].Category.Name < groups[j].Category.Name
	})

	// `limit` caps the total across groups; trim whole groups once it is spent.
	total := 0
	kept := make([]groupJSON, 0, len(groups))
	for _, g := range groups {
		if total >= limit {
			break
		}
		if room := limit - total; len(g.Products) > room {
			g.Products = g.Products[:room]
		}
		g.Count = len(g.Products)
		total += g.Count
		kept = append(kept, g)
	}
	return productListJSON{Groups: kept, Count: total}
}

func (s *Server) GetProduct(w http.ResponseWriter, r *http.Request) {
	id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
	if err != nil {
		writeError(w, http.StatusBadRequest, CodeInvalidRequest, "Product id must be an integer.")
		return
	}
	product, err := s.store.Product(r.Context(), id)
	if errors.Is(err, store.ErrNotFound) {
		writeError(w, http.StatusNotFound, CodeProductNotFound,
			"Product "+strconv.FormatInt(id, 10)+" does not exist.")
		return
	}
	if err != nil {
		writeInternal(w, "get product", err)
		return
	}
	writeJSON(w, http.StatusOK, toProduct(*product, true))
}

// intParam parses an optional bounded integer, returning fallback when empty.
func intParam(raw string, fallback, min, max int) (int, error) {
	if raw == "" {
		return fallback, nil
	}
	v, err := strconv.Atoi(raw)
	if err != nil || v < min || v > max {
		return 0, errors.New("out of range")
	}
	return v, nil
}

func optionalInt(raw string) (*int, error) {
	if raw == "" {
		return nil, nil
	}
	v, err := strconv.Atoi(raw)
	if err != nil || v < 0 {
		return nil, errors.New("invalid")
	}
	return &v, nil
}
