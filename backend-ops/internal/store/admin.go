package store

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"
)

var ErrNothingToUpdate = errors.New("no fields to update")

// ---------- dashboard stats ----------

type Totals struct {
	Products        int `json:"products"`
	ActiveProducts  int `json:"active_products"`
	Categories      int `json:"categories"`
	Sizes           int `json:"sizes"`
	Images          int `json:"images"`
	Users           int `json:"users"`
	Orders          int `json:"orders"`
	RevenueJPY      int `json:"revenue_jpy"`
	OpenCartLines   int `json:"open_cart_lines"`
	CancelledOrders int `json:"cancelled_orders"`
}

type CategoryCount struct {
	Slug  string `json:"slug"`
	Name  string `json:"name"`
	Count int    `json:"count"`
}

type DayPoint struct {
	Date       string `json:"date"`
	Orders     int    `json:"orders"`
	RevenueJPY int    `json:"revenue_jpy"`
}

type TopProduct struct {
	ProductID   *int64 `json:"product_id"`
	ProductName string `json:"product_name"`
	Quantity    int    `json:"quantity"`
	RevenueJPY  int    `json:"revenue_jpy"`
}

type PriceBucket struct {
	Label string `json:"label"`
	Count int    `json:"count"`
}

type Stats struct {
	Totals             Totals          `json:"totals"`
	ProductsByCategory []CategoryCount `json:"products_by_category"`
	OrdersByDay        []DayPoint      `json:"orders_by_day"`
	TopProducts        []TopProduct    `json:"top_products"`
	PriceBuckets       []PriceBucket   `json:"price_buckets"`
}

// Stats gathers everything the dashboard renders, including the series behind
// its charts. Cancelled orders are excluded from revenue but still counted.
func (s *Store) Stats(ctx context.Context, days int) (Stats, error) {
	var out Stats
	if err := s.pool.QueryRow(ctx, `
		SELECT (SELECT COUNT(*) FROM products),
		       (SELECT COUNT(*) FROM products WHERE is_active),
		       (SELECT COUNT(*) FROM categories),
		       (SELECT COUNT(*) FROM product_sizes),
		       (SELECT COUNT(*) FROM product_images),
		       (SELECT COUNT(*) FROM users),
		       (SELECT COUNT(*) FROM orders),
		       (SELECT COALESCE(SUM(total_jpy),0) FROM orders WHERE status <> 'cancelled'),
		       (SELECT COUNT(*) FROM cart_items),
		       (SELECT COUNT(*) FROM orders WHERE status = 'cancelled')`,
	).Scan(&out.Totals.Products, &out.Totals.ActiveProducts, &out.Totals.Categories,
		&out.Totals.Sizes, &out.Totals.Images, &out.Totals.Users, &out.Totals.Orders,
		&out.Totals.RevenueJPY, &out.Totals.OpenCartLines, &out.Totals.CancelledOrders); err != nil {
		return Stats{}, fmt.Errorf("totals: %w", err)
	}

	out.ProductsByCategory = []CategoryCount{}
	rows, err := s.pool.Query(ctx, `
		SELECT c.slug, c.name, COUNT(p.id)
		FROM categories c
		LEFT JOIN products p ON p.category_id = c.id
		GROUP BY c.id, c.slug, c.name
		ORDER BY COUNT(p.id) DESC, c.name`)
	if err != nil {
		return Stats{}, fmt.Errorf("products by category: %w", err)
	}
	for rows.Next() {
		var c CategoryCount
		if err := rows.Scan(&c.Slug, &c.Name, &c.Count); err != nil {
			rows.Close()
			return Stats{}, err
		}
		out.ProductsByCategory = append(out.ProductsByCategory, c)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return Stats{}, err
	}

	// generate_series fills days with no orders, so the chart has no gaps.
	out.OrdersByDay = []DayPoint{}
	rows, err = s.pool.Query(ctx, `
		SELECT to_char(d.day, 'YYYY-MM-DD'),
		       COUNT(o.id),
		       COALESCE(SUM(o.total_jpy) FILTER (WHERE o.status <> 'cancelled'), 0)
		FROM generate_series(
		         (NOW() AT TIME ZONE 'UTC')::date - ($1::int - 1),
		         (NOW() AT TIME ZONE 'UTC')::date,
		         '1 day') AS d(day)
		LEFT JOIN orders o ON (o.created_at AT TIME ZONE 'UTC')::date = d.day
		GROUP BY d.day
		ORDER BY d.day`, days)
	if err != nil {
		return Stats{}, fmt.Errorf("orders by day: %w", err)
	}
	for rows.Next() {
		var p DayPoint
		if err := rows.Scan(&p.Date, &p.Orders, &p.RevenueJPY); err != nil {
			rows.Close()
			return Stats{}, err
		}
		out.OrdersByDay = append(out.OrdersByDay, p)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return Stats{}, err
	}

	out.TopProducts = []TopProduct{}
	rows, err = s.pool.Query(ctx, `
		SELECT oi.product_id, oi.product_name,
		       SUM(oi.quantity)::int, SUM(oi.subtotal_jpy)::int
		FROM order_items oi
		JOIN orders o ON o.id = oi.order_id AND o.status <> 'cancelled'
		GROUP BY oi.product_id, oi.product_name
		ORDER BY 4 DESC
		LIMIT 10`)
	if err != nil {
		return Stats{}, fmt.Errorf("top products: %w", err)
	}
	for rows.Next() {
		var p TopProduct
		if err := rows.Scan(&p.ProductID, &p.ProductName, &p.Quantity, &p.RevenueJPY); err != nil {
			rows.Close()
			return Stats{}, err
		}
		out.TopProducts = append(out.TopProducts, p)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return Stats{}, err
	}

	out.PriceBuckets = []PriceBucket{}
	rows, err = s.pool.Query(ctx, `
		SELECT label, COUNT(*)::int FROM (
			SELECT CASE
			         WHEN u <   500 THEN 1
			         WHEN u <  1000 THEN 2
			         WHEN u <  3000 THEN 3
			         WHEN u < 10000 THEN 4
			         ELSE 5 END AS ord,
			       CASE
			         WHEN u <   500 THEN 'under 500'
			         WHEN u <  1000 THEN '500-999'
			         WHEN u <  3000 THEN '1,000-2,999'
			         WHEN u < 10000 THEN '3,000-9,999'
			         ELSE '10,000+' END AS label
			FROM (SELECT p.base_price_jpy + ps.price_adjustment_jpy AS u
			      FROM products p JOIN product_sizes ps ON ps.product_id = p.id) t
		) b
		GROUP BY ord, label ORDER BY ord`)
	if err != nil {
		return Stats{}, fmt.Errorf("price buckets: %w", err)
	}
	defer rows.Close()
	for rows.Next() {
		var b PriceBucket
		if err := rows.Scan(&b.Label, &b.Count); err != nil {
			return Stats{}, err
		}
		out.PriceBuckets = append(out.PriceBuckets, b)
	}
	return out, rows.Err()
}

// ---------- orders ----------

type AdminOrder struct {
	Order
	UserID    int64
	UserName  string
	UserEmail string
}

// OrderFilter narrows an admin order list. Every field is optional; a nil or
// empty one is simply not part of the WHERE clause.
type OrderFilter struct {
	// Query matches the order number, the customer's name, or their email --
	// the three things someone has in hand when hunting for one order.
	Query string
	// Statuses matches any of the given statuses. Empty means all of them --
	// an admin asking for "pending and cancelled" is one query, not two.
	Statuses []string
	// Totals are order totals in yen, inclusive.
	MinTotalJPY *int
	MaxTotalJPY *int
	// From is inclusive, To exclusive -- the handler turns a "to" date into
	// the start of the following day so the named day is included whole.
	From *time.Time
	To   *time.Time
	// Quantity bounds count UNITS ordered (the sum of item quantities), not
	// the number of distinct lines. "Orders of 20 or more" means twenty things.
	MinQuantity *int
	MaxQuantity *int

	Limit  int
	Offset int
}

// AllOrders lists every user's orders, newest first.
func (s *Store) AllOrders(ctx context.Context, f OrderFilter) ([]AdminOrder, int, error) {
	clauses := []string{"TRUE"}
	args := []any{}

	add := func(sql string, value any) {
		args = append(args, value)
		clauses = append(clauses, fmt.Sprintf(sql, len(args)))
	}
	if f.Query != "" {
		add("(o.order_number ILIKE $%[1]d OR u.name ILIKE $%[1]d OR u.email ILIKE $%[1]d)",
			"%"+f.Query+"%")
	}
	if len(f.Statuses) > 0 {
		add("o.status = ANY($%d)", f.Statuses)
	}
	if f.MinTotalJPY != nil {
		add("o.total_jpy >= $%d", *f.MinTotalJPY)
	}
	if f.MaxTotalJPY != nil {
		add("o.total_jpy <= $%d", *f.MaxTotalJPY)
	}
	if f.From != nil {
		add("o.created_at >= $%d", *f.From)
	}
	if f.To != nil {
		add("o.created_at < $%d", *f.To)
	}
	// Units live one table away, so both bounds go through the same scalar
	// subquery rather than a GROUP BY -- the outer query must stay one row per
	// order, and an order with no items must still compare as zero.
	const units = "(SELECT COALESCE(SUM(quantity), 0) FROM order_items WHERE order_id = o.id)"
	if f.MinQuantity != nil {
		add(units+" >= $%d", *f.MinQuantity)
	}
	if f.MaxQuantity != nil {
		add(units+" <= $%d", *f.MaxQuantity)
	}
	where := strings.Join(clauses, " AND ")

	var total int
	if err := s.pool.QueryRow(ctx,
		`SELECT COUNT(*) FROM orders o JOIN users u ON u.id = o.user_id
		 WHERE `+where, args...).Scan(&total); err != nil {
		return nil, 0, fmt.Errorf("count orders: %w", err)
	}

	args = append(args, f.Limit, f.Offset)
	rows, err := s.pool.Query(ctx, fmt.Sprintf(`
		SELECT o.id, o.order_number, o.status, o.shipping_address, o.total_jpy,
		       o.created_at, u.id, u.name, u.email
		FROM orders o JOIN users u ON u.id = o.user_id
		WHERE %s
		ORDER BY o.id DESC
		LIMIT $%d OFFSET $%d`, where, len(args)-1, len(args)), args...)
	if err != nil {
		return nil, 0, fmt.Errorf("query orders: %w", err)
	}
	defer rows.Close()

	orders := []AdminOrder{}
	ids := []int64{}
	index := map[int64]int{}
	for rows.Next() {
		var o AdminOrder
		var id int64
		if err := rows.Scan(&id, &o.OrderNumber, &o.Status, &o.ShippingAddress,
			&o.TotalJPY, &o.CreatedAt, &o.UserID, &o.UserName, &o.UserEmail); err != nil {
			return nil, 0, fmt.Errorf("scan order: %w", err)
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
		return nil, 0, fmt.Errorf("query order items: %w", err)
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

// UpdateOrderStatus moves an order between pending/confirmed/cancelled.
func (s *Store) UpdateOrderStatus(ctx context.Context, orderNumber, status string) error {
	tag, err := s.pool.Exec(ctx,
		`UPDATE orders SET status = $2 WHERE order_number = $1`, orderNumber, status)
	if err != nil {
		return fmt.Errorf("update order status: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return ErrOrderNotFound
	}
	return nil
}

// ---------- users ----------

type AdminUser struct {
	ID        int64     `json:"id"`
	Name      string    `json:"name"`
	Email     string    `json:"email"`
	CreatedAt time.Time `json:"created_at"`
	IsAdmin   bool      `json:"is_admin"`
	CartLines int       `json:"cart_lines"`
	Orders    int       `json:"orders"`
	SpentJPY  int       `json:"spent_jpy"`
}

// UserFilter narrows an admin user list. Every field is optional, and the
// numeric bounds read the same derived figures the rows display -- filtering
// on a number the table does not show would be untraceable.
type UserFilter struct {
	// Query matches name or email.
	Query string
	// Role is "admin", "customer", or empty for both.
	Role string
	// HasCart keeps only accounts with something left in the basket.
	HasCart bool

	MinOrders   *int
	MaxOrders   *int
	MinSpentJPY *int
	MaxSpentJPY *int
	// From is inclusive, To exclusive, over the signup date.
	From *time.Time
	To   *time.Time

	Limit  int
	Offset int
}

// The three derived figures, defined once: the WHERE clause and the SELECT
// must agree, or a filter would keep rows whose displayed number contradicts it.
const (
	sqlCartLines = "(SELECT COUNT(*) FROM cart_items ci WHERE ci.user_id = u.id)"
	sqlOrders    = "(SELECT COUNT(*) FROM orders o WHERE o.user_id = u.id)"
	sqlSpent     = `(SELECT COALESCE(SUM(o.total_jpy),0) FROM orders o
	                  WHERE o.user_id = u.id AND o.status <> 'cancelled')`
)

func (s *Store) AllUsers(ctx context.Context, f UserFilter) ([]AdminUser, int, error) {
	clauses := []string{"TRUE"}
	args := []any{}
	add := func(sql string, value any) {
		args = append(args, value)
		clauses = append(clauses, fmt.Sprintf(sql, len(args)))
	}
	if f.Query != "" {
		add("(u.name ILIKE $%[1]d OR u.email ILIKE $%[1]d)", "%"+f.Query+"%")
	}
	switch f.Role {
	case "admin":
		clauses = append(clauses, "u.is_admin")
	case "customer":
		clauses = append(clauses, "NOT u.is_admin")
	}
	if f.HasCart {
		clauses = append(clauses, sqlCartLines+" > 0")
	}
	if f.MinOrders != nil {
		add(sqlOrders+" >= $%d", *f.MinOrders)
	}
	if f.MaxOrders != nil {
		add(sqlOrders+" <= $%d", *f.MaxOrders)
	}
	if f.MinSpentJPY != nil {
		add(sqlSpent+" >= $%d", *f.MinSpentJPY)
	}
	if f.MaxSpentJPY != nil {
		add(sqlSpent+" <= $%d", *f.MaxSpentJPY)
	}
	if f.From != nil {
		add("u.created_at >= $%d", *f.From)
	}
	if f.To != nil {
		add("u.created_at < $%d", *f.To)
	}
	where := strings.Join(clauses, " AND ")

	var total int
	if err := s.pool.QueryRow(ctx,
		`SELECT COUNT(*) FROM users u WHERE `+where, args...).Scan(&total); err != nil {
		return nil, 0, fmt.Errorf("count users: %w", err)
	}

	args = append(args, f.Limit, f.Offset)
	rows, err := s.pool.Query(ctx, fmt.Sprintf(`
		SELECT u.id, u.name, u.email, u.created_at, u.is_admin,
		       %s, %s, %s
		FROM users u WHERE %s
		ORDER BY u.id LIMIT $%d OFFSET $%d`,
		sqlCartLines, sqlOrders, sqlSpent, where, len(args)-1, len(args)), args...)
	if err != nil {
		return nil, 0, fmt.Errorf("query users: %w", err)
	}
	defer rows.Close()

	out := []AdminUser{}
	for rows.Next() {
		var u AdminUser
		if err := rows.Scan(&u.ID, &u.Name, &u.Email, &u.CreatedAt, &u.IsAdmin,
			&u.CartLines, &u.Orders, &u.SpentJPY); err != nil {
			return nil, 0, err
		}
		out = append(out, u)
	}
	return out, total, rows.Err()
}

// ---------- product management ----------

type ProductUpdate struct {
	Name         *string
	Description  *string
	BasePriceJPY *int
	IsActive     *bool
}

func (u ProductUpdate) empty() bool {
	return u.Name == nil && u.Description == nil && u.BasePriceJPY == nil && u.IsActive == nil
}

// UpdateProduct applies a partial update. COALESCE leaves omitted fields
// untouched, so a caller never has to send the whole product back.
func (s *Store) UpdateProduct(ctx context.Context, id int64, u ProductUpdate) error {
	if u.empty() {
		return ErrNothingToUpdate
	}
	tag, err := s.pool.Exec(ctx, `
		UPDATE products SET
			name           = COALESCE($2, name),
			description    = COALESCE($3, description),
			base_price_jpy = COALESCE($4, base_price_jpy),
			is_active      = COALESCE($5, is_active),
			updated_at     = NOW()
		WHERE id = $1`, id, u.Name, u.Description, u.BasePriceJPY, u.IsActive)
	if err != nil {
		return fmt.Errorf("update product: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

type SizeUpdate struct {
	SizeName           *string
	PriceAdjustmentJPY *int
}

func (s *Store) UpdateSize(ctx context.Context, id int64, u SizeUpdate) error {
	if u.SizeName == nil && u.PriceAdjustmentJPY == nil {
		return ErrNothingToUpdate
	}
	tag, err := s.pool.Exec(ctx, `
		UPDATE product_sizes SET
			size_name            = COALESCE($2, size_name),
			price_adjustment_jpy = COALESCE($3, price_adjustment_jpy)
		WHERE id = $1`, id, u.SizeName, u.PriceAdjustmentJPY)
	if err != nil {
		return fmt.Errorf("update size: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return ErrSizeNotFound
	}
	return nil
}

// DeleteProduct removes a product. order_items references it with ON DELETE
// RESTRICT, so a product that has ever been ordered cannot be deleted --
// deactivate it instead.
func (s *Store) DeleteProduct(ctx context.Context, id int64) error {
	tag, err := s.pool.Exec(ctx, `DELETE FROM products WHERE id = $1`, id)
	if err != nil {
		var pgErr interface{ SQLState() string }
		if errors.As(err, &pgErr) && pgErr.SQLState() == "23503" {
			return ErrProductInUse
		}
		return fmt.Errorf("delete product: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

var ErrProductInUse = errors.New("product is referenced by an order")
