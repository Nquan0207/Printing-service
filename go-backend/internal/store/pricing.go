package store

import (
	"context"
	"errors"
	"fmt"

	"github.com/jackc/pgx/v5"
)

// ErrSizeNotFound means the size id is unknown, or belongs to a different
// product. Both are the caller's mistake and must not be reported as a
// missing product.
var ErrSizeNotFound = errors.New("size not found")

// PricedSize is one (product, size) pair with its unit price resolved.
type PricedSize struct {
	ProductID    int64
	ProductName  string
	SizeID       int64
	SizeName     string
	UnitPriceJPY int
}

// PricedSize resolves a product/size pair, verifying the size actually belongs
// to that product.
func (s *Store) PricedSize(ctx context.Context, productID, sizeID int64) (*PricedSize, error) {
	out := PricedSize{ProductID: productID, SizeID: sizeID}
	err := s.pool.QueryRow(ctx, `
		SELECT p.name, ps.size_name, p.base_price_jpy + ps.price_adjustment_jpy
		FROM products p
		JOIN product_sizes ps ON ps.product_id = p.id
		WHERE p.id = $1 AND ps.id = $2 AND p.is_active`,
		productID, sizeID,
	).Scan(&out.ProductName, &out.SizeName, &out.UnitPriceJPY)

	if errors.Is(err, pgx.ErrNoRows) {
		// No match could mean either input was wrong; tell them apart so the
		// caller gets product_not_found vs size_not_found correctly.
		var exists bool
		if err := s.pool.QueryRow(ctx,
			`SELECT EXISTS (SELECT 1 FROM products WHERE id = $1 AND is_active)`,
			productID,
		).Scan(&exists); err != nil {
			return nil, fmt.Errorf("check product %d: %w", productID, err)
		}
		if !exists {
			return nil, ErrNotFound
		}
		return nil, ErrSizeNotFound
	}
	if err != nil {
		return nil, fmt.Errorf("query priced size: %w", err)
	}
	return &out, nil
}
