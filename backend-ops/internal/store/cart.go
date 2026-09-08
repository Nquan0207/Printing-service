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
	ID          int64
	ProductID   int64
	ProductName string
	SizeID      int64
	SizeName    string
	ImageKey    *string
	Quantity    int
	// Sizes is every size of this product with its resolved unit price, so a
	// caller can offer a size switch without fetching the product again.
	// Ordered by price adjustment, never by name -- alphabetical gives L, M, S.
	Sizes        []PricedSize
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
	if err := rows.Err(); err != nil {
		return Cart{}, err
	}

	// One extra query for the whole cart rather than one per line.
	for i := range out.Items {
		sizes, err := s.productSizes(ctx, out.Items[i].ProductID)
		if err != nil {
			return Cart{}, err
		}
		out.Items[i].Sizes = sizes
	}
	return out, nil
}

// productSizes lists a product's sizes with unit prices resolved.
//
// Ordered by price_adjustment_jpy: there is no display_order column, and
// ordering by size_name would give L, M, S.
func (s *Store) productSizes(ctx context.Context, productID int64) ([]PricedSize, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT ps.id, ps.size_name, p.base_price_jpy + ps.price_adjustment_jpy
		FROM product_sizes ps
		JOIN products p ON p.id = ps.product_id
		WHERE ps.product_id = $1
		ORDER BY ps.price_adjustment_jpy, ps.id`, productID)
	if err != nil {
		return nil, fmt.Errorf("query product sizes: %w", err)
	}
	defer rows.Close()

	out := []PricedSize{}
	for rows.Next() {
		ps := PricedSize{ProductID: productID}
		if err := rows.Scan(&ps.SizeID, &ps.SizeName, &ps.UnitPriceJPY); err != nil {
			return nil, fmt.Errorf("scan product size: %w", err)
		}
		out = append(out, ps)
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

// UpdateCartItem changes one line's size and quantity, scoped to its owner.
//
// Changing the size can collide with a line the cart already holds for the
// same product, because UNIQUE(user_id, product_id, product_size_id) allows
// only one. That is merged rather than refused: a shopper who switches an S to
// an M they already have means "make it all M", not "fail". The whole thing is
// one transaction so a merge can never delete the source line and then fail to
// add its quantity.
func (s *Store) UpdateCartItem(
	ctx context.Context, userID, itemID, sizeID int64, quantity int,
) error {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("begin: %w", err)
	}
	defer tx.Rollback(ctx) //nolint:errcheck // no-op once committed

	// Locked so a concurrent add to the same product cannot slip between the
	// collision check and the merge.
	var productID int64
	err = tx.QueryRow(ctx,
		`SELECT product_id FROM cart_items WHERE id = $1 AND user_id = $2 FOR UPDATE`,
		itemID, userID).Scan(&productID)
	if errors.Is(err, pgx.ErrNoRows) {
		return ErrCartItemNotFound
	}
	if err != nil {
		return fmt.Errorf("read cart item: %w", err)
	}

	// The size must belong to THIS product; otherwise a caller could price a
	// line against another product's ladder.
	if _, err := pricedSizeTx(ctx, tx, productID, sizeID); err != nil {
		return err
	}

	var otherID int64
	var otherQty int
	err = tx.QueryRow(ctx, `
		SELECT id, quantity FROM cart_items
		WHERE user_id = $1 AND product_id = $2 AND product_size_id = $3 AND id <> $4
		FOR UPDATE`, userID, productID, sizeID, itemID).Scan(&otherID, &otherQty)
	switch {
	case err == nil:
		// Fold this line into the one that already holds that size.
		if _, err := tx.Exec(ctx,
			`UPDATE cart_items SET quantity = $1, updated_at = NOW() WHERE id = $2`,
			otherQty+quantity, otherID); err != nil {
			return fmt.Errorf("merge cart item: %w", err)
		}
		if _, err := tx.Exec(ctx, `DELETE FROM cart_items WHERE id = $1`, itemID); err != nil {
			return fmt.Errorf("drop merged cart item: %w", err)
		}
	case errors.Is(err, pgx.ErrNoRows):
		if _, err := tx.Exec(ctx, `
			UPDATE cart_items SET product_size_id = $1, quantity = $2, updated_at = NOW()
			WHERE id = $3`, sizeID, quantity, itemID); err != nil {
			return fmt.Errorf("update cart item: %w", err)
		}
	default:
		return fmt.Errorf("check cart line collision: %w", err)
	}

	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("commit: %w", err)
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
