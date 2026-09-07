package store

import (
	"context"
	"errors"
	"fmt"

	"github.com/jackc/pgx/v5"
)

// ErrCartItemNotFound means the line does not exist, or belongs to another
// user. Both must read as "not found" so a caller cannot probe for the
// existence of someone else's cart lines.
var ErrCartItemNotFound = errors.New("cart item not found")

type CartItem struct {
	ID           int64
	ProductID    int64
	ProductName  string
	SizeID       int64
	SizeName     string
	ImageKey     *string
	Quantity     int
	UnitPriceJPY int
}

type Cart struct {
	Items    []CartItem
	TotalJPY int
}

// Cart returns every line for one user, priced at current catalog prices.
func (s *Store) Cart(ctx context.Context, userID int64) (Cart, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT ci.id, p.id, p.name, ps.id, ps.size_name,
		       (SELECT pi.image_key FROM product_images pi
		         WHERE pi.product_id = p.id ORDER BY pi.id LIMIT 1),
		       ci.quantity, p.base_price_jpy + ps.price_adjustment_jpy
		FROM cart_items ci
		JOIN products p       ON p.id  = ci.product_id
		JOIN product_sizes ps ON ps.id = ci.product_size_id
		WHERE ci.user_id = $1
		ORDER BY ci.id`, userID)
	if err != nil {
		return Cart{}, fmt.Errorf("query cart: %w", err)
	}
	defer rows.Close()

	out := Cart{Items: []CartItem{}}
	for rows.Next() {
		var it CartItem
		if err := rows.Scan(&it.ID, &it.ProductID, &it.ProductName, &it.SizeID,
			&it.SizeName, &it.ImageKey, &it.Quantity, &it.UnitPriceJPY); err != nil {
			return Cart{}, fmt.Errorf("scan cart item: %w", err)
		}
		out.Items = append(out.Items, it)
		out.TotalJPY += it.UnitPriceJPY * it.Quantity
	}
	return out, rows.Err()
}

// AddToCart adds quantity to an existing line for the same (product, size),
// or creates one. UNIQUE(user_id, product_id, product_size_id) makes this an
// upsert; POST adds rather than replaces, per the contract.
func (s *Store) AddToCart(ctx context.Context, userID, productID, sizeID int64, quantity int) error {
	// Validates that the size really belongs to the product, so a mismatched
	// pair is rejected before it can reach the cart.
	if _, err := s.PricedSize(ctx, productID, sizeID); err != nil {
		return err
	}
	_, err := s.pool.Exec(ctx, `
		INSERT INTO cart_items (user_id, product_id, product_size_id, quantity)
		VALUES ($1, $2, $3, $4)
		ON CONFLICT (user_id, product_id, product_size_id)
		DO UPDATE SET quantity   = cart_items.quantity + EXCLUDED.quantity,
		              updated_at = NOW()`,
		userID, productID, sizeID, quantity)
	if err != nil {
		return fmt.Errorf("add to cart: %w", err)
	}
	return nil
}

// RemoveCartItem deletes one line, scoped to its owner.
func (s *Store) RemoveCartItem(ctx context.Context, userID, itemID int64) error {
	tag, err := s.pool.Exec(ctx,
		`DELETE FROM cart_items WHERE id = $1 AND user_id = $2`, itemID, userID)
	if err != nil {
		return fmt.Errorf("remove cart item: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return ErrCartItemNotFound
	}
	return nil
}

// clearCart is used by checkout, inside the order transaction.
func clearCart(ctx context.Context, tx pgx.Tx, userID int64) error {
	if _, err := tx.Exec(ctx, `DELETE FROM cart_items WHERE user_id = $1`, userID); err != nil {
		return fmt.Errorf("clear cart: %w", err)
	}
	return nil
}
