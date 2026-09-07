package store

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
)

var (
	ErrCartEmpty     = errors.New("cart is empty")
	ErrOrderNotFound = errors.New("order not found")
	ErrOrderTooLarge = errors.New("order total exceeds the storable maximum")
)

// maxOrderJPY matches the INTEGER columns in schema.sql (total_jpy,
// subtotal_jpy). Checked before INSERT so an oversized cart fails legibly
// instead of as a constraint error mid-transaction.
const maxOrderJPY = 2147483647

type OrderItem struct {
	ProductID    *int64
	ProductName  string
	SizeName     string
	Quantity     int
	UnitPriceJPY int
	SubtotalJPY  int
}

type Order struct {
	OrderNumber     string
	Status          string
	ShippingAddress string
	TotalJPY        int
	Items           []OrderItem
	CreatedAt       time.Time
}

// PlaceOrder converts the user's cart into an order in one transaction:
// insert the order, snapshot every line, clear the cart. Either all of it
// happens or none of it does -- a half-placed order with a drained cart would
// lose the customer's basket.
func (s *Store) PlaceOrder(ctx context.Context, userID int64, shippingAddress string) (Order, error) {
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return Order{}, fmt.Errorf("begin: %w", err)
	}
	defer tx.Rollback(ctx) //nolint:errcheck // no-op once committed

	cart, err := cartTx(ctx, tx, userID)
	if err != nil {
		return Order{}, err
	}
	if len(cart.Items) == 0 {
		return Order{}, ErrCartEmpty
	}
	if cart.TotalJPY > maxOrderJPY {
		return Order{}, ErrOrderTooLarge
	}

	number, err := nextOrderNumber(ctx, tx)
	if err != nil {
		return Order{}, err
	}

	out := Order{
		OrderNumber:     number,
		Status:          "confirmed",
		ShippingAddress: shippingAddress,
		TotalJPY:        cart.TotalJPY,
		Items:           make([]OrderItem, 0, len(cart.Items)),
	}
	var orderID int64
	if err := tx.QueryRow(ctx, `
		INSERT INTO orders (user_id, order_number, status, shipping_address, total_jpy)
		VALUES ($1, $2, 'confirmed', $3, $4)
		RETURNING id, created_at`,
		userID, number, shippingAddress, cart.TotalJPY,
	).Scan(&orderID, &out.CreatedAt); err != nil {
		return Order{}, fmt.Errorf("insert order: %w", err)
	}

	for _, item := range cart.Items {
		// product_name, size_name and unit_price are copied, not referenced:
		// order history must not shift when the catalog is re-crawled.
		line := OrderItem{
			ProductID:    &item.ProductID,
			ProductName:  item.ProductName,
			SizeName:     item.SizeName,
			Quantity:     item.Quantity,
			UnitPriceJPY: item.UnitPriceJPY,
			SubtotalJPY:  item.UnitPriceJPY * item.Quantity,
		}
		if _, err := tx.Exec(ctx, `
			INSERT INTO order_items (order_id, product_id, product_size_id,
			                         product_name, size_name, quantity,
			                         unit_price_jpy, subtotal_jpy)
			VALUES ($1, $2, $3, $4, $5, $6, $7, $8)`,
			orderID, item.ProductID, item.SizeID, line.ProductName, line.SizeName,
			line.Quantity, line.UnitPriceJPY, line.SubtotalJPY,
		); err != nil {
			return Order{}, fmt.Errorf("insert order item: %w", err)
		}
		out.Items = append(out.Items, line)
	}

	if err := clearCart(ctx, tx, userID); err != nil {
		return Order{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return Order{}, fmt.Errorf("commit: %w", err)
	}
	return out, nil
}

// nextOrderNumber produces RKS-YYYYMMDD-NNNN. The advisory lock is held for
// the transaction so two concurrent checkouts cannot pick the same suffix and
// collide on the UNIQUE constraint.
func nextOrderNumber(ctx context.Context, tx pgx.Tx) (string, error) {
	// UTC so the date in the number always matches created_at, which the
	// contract specifies as RFC 3339 UTC.
	day := time.Now().UTC().Format("20060102")
	if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock(hashtext($1))`, "order-number-"+day); err != nil {
		return "", fmt.Errorf("lock order numbering: %w", err)
	}
	var count int
	if err := tx.QueryRow(ctx,
		`SELECT COUNT(*) FROM orders WHERE order_number LIKE $1`, "RKS-"+day+"-%",
	).Scan(&count); err != nil {
		return "", fmt.Errorf("count today's orders: %w", err)
	}
	return fmt.Sprintf("RKS-%s-%04d", day, count+1), nil
}

// cartTx reads the cart inside the checkout transaction, locking the lines so
// a concurrent add cannot slip in between pricing and clearing.
func cartTx(ctx context.Context, tx pgx.Tx, userID int64) (Cart, error) {
	rows, err := tx.Query(ctx, `
		SELECT ci.id, p.id, p.name, ps.id, ps.size_name,
		       ci.quantity, p.base_price_jpy + ps.price_adjustment_jpy
		FROM cart_items ci
		JOIN products p       ON p.id  = ci.product_id
		JOIN product_sizes ps ON ps.id = ci.product_size_id
		WHERE ci.user_id = $1
		ORDER BY ci.id
		FOR UPDATE OF ci`, userID)
	if err != nil {
		return Cart{}, fmt.Errorf("lock cart: %w", err)
	}
	defer rows.Close()

	out := Cart{Items: []CartItem{}}
	for rows.Next() {
		var it CartItem
		if err := rows.Scan(&it.ID, &it.ProductID, &it.ProductName, &it.SizeID,
			&it.SizeName, &it.Quantity, &it.UnitPriceJPY); err != nil {
			return Cart{}, fmt.Errorf("scan cart item: %w", err)
		}
		out.Items = append(out.Items, it)
		out.TotalJPY += it.UnitPriceJPY * it.Quantity
	}
	return out, rows.Err()
}

// UserOrders lists one shopper's own orders, newest first.
//
// Items are fetched for the whole page in a second query rather than one per
// order: a history of twenty orders would otherwise be twenty-one round trips.
func (s *Store) UserOrders(ctx context.Context, userID int64, limit, offset int) ([]Order, int, error) {
	var total int
	if err := s.pool.QueryRow(ctx,
		`SELECT COUNT(*) FROM orders WHERE user_id = $1`, userID).Scan(&total); err != nil {
		return nil, 0, fmt.Errorf("count user orders: %w", err)
	}

	rows, err := s.pool.Query(ctx, `
		SELECT id, order_number, status, shipping_address, total_jpy, created_at
		FROM orders WHERE user_id = $1
		ORDER BY id DESC LIMIT $2 OFFSET $3`, userID, limit, offset)
	if err != nil {
		return nil, 0, fmt.Errorf("query user orders: %w", err)
	}
	defer rows.Close()

	orders := []Order{}
	ids := []int64{}
	index := map[int64]int{}
	for rows.Next() {
		var o Order
		var id int64
		if err := rows.Scan(&id, &o.OrderNumber, &o.Status, &o.ShippingAddress,
			&o.TotalJPY, &o.CreatedAt); err != nil {
			return nil, 0, fmt.Errorf("scan user order: %w", err)
		}
		o.Items = []OrderItem{}
		index[id] = len(orders)
		ids = append(ids, id)
		orders = append(orders, o)
	}
	if err := rows.Err(); err != nil {
		return nil, 0, err
	}
	if len(ids) == 0 {
		return orders, total, nil
	}

	itemRows, err := s.pool.Query(ctx, `
		SELECT order_id, product_id, product_name, size_name, quantity,
		       unit_price_jpy, subtotal_jpy
		FROM order_items WHERE order_id = ANY($1) ORDER BY order_id, id`, ids)
	if err != nil {
		return nil, 0, fmt.Errorf("query user order items: %w", err)
	}
	defer itemRows.Close()
	for itemRows.Next() {
		var orderID int64
		var it OrderItem
		if err := itemRows.Scan(&orderID, &it.ProductID, &it.ProductName, &it.SizeName,
			&it.Quantity, &it.UnitPriceJPY, &it.SubtotalJPY); err != nil {
			return nil, 0, err
		}
		if i, ok := index[orderID]; ok {
			orders[i].Items = append(orders[i].Items, it)
		}
	}
	return orders, total, itemRows.Err()
}

// Order returns one order, scoped to its owner.
func (s *Store) Order(ctx context.Context, userID int64, orderNumber string) (Order, error) {
	var out Order
	var orderID int64
	err := s.pool.QueryRow(ctx, `
		SELECT id, order_number, status, shipping_address, total_jpy, created_at
		FROM orders WHERE order_number = $1 AND user_id = $2`,
		orderNumber, userID,
	).Scan(&orderID, &out.OrderNumber, &out.Status, &out.ShippingAddress,
		&out.TotalJPY, &out.CreatedAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return Order{}, ErrOrderNotFound
	}
	if err != nil {
		return Order{}, fmt.Errorf("query order: %w", err)
	}

	rows, err := s.pool.Query(ctx, `
		SELECT product_id, product_name, size_name, quantity, unit_price_jpy, subtotal_jpy
		FROM order_items WHERE order_id = $1 ORDER BY id`, orderID)
	if err != nil {
		return Order{}, fmt.Errorf("query order items: %w", err)
	}
	defer rows.Close()

	out.Items = []OrderItem{}
	for rows.Next() {
		var it OrderItem
		if err := rows.Scan(&it.ProductID, &it.ProductName, &it.SizeName,
			&it.Quantity, &it.UnitPriceJPY, &it.SubtotalJPY); err != nil {
			return Order{}, fmt.Errorf("scan order item: %w", err)
		}
		out.Items = append(out.Items, it)
	}
	return out, rows.Err()
}
