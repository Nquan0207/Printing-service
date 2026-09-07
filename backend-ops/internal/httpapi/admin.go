package httpapi

import (
	"errors"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/octguy/stockroom/internal/store"
)

// Admin endpoints are UNAUTHENTICATED, exactly like the rest of the service:
// there is no auth in the PoC and the port is loopback-only. They are grouped
// under /api/v1/admin so a single middleware can gate them the moment real
// auth exists. See docs/api-contract.md#the-trust-boundary.

const (
	defaultAdminLimit = 50
	maxAdminLimit     = 500
	defaultStatsDays  = 30
)

func (s *Server) AdminStats(w http.ResponseWriter, r *http.Request) {
	days, err := intParam(r.URL.Query().Get("days"), defaultStatsDays, 1, 365)
	if err != nil {
		writeError(w, http.StatusBadRequest, CodeInvalidRequest, "days must be between 1 and 365.")
		return
	}
	stats, err := s.store.Stats(r.Context(), days)
	if err != nil {
		writeInternal(w, "admin stats", err)
		return
	}
	writeJSON(w, http.StatusOK, stats)
}

type adminOrderJSON struct {
	orderJSON
	UserID    int64  `json:"user_id"`
	UserName  string `json:"user_name"`
	UserEmail string `json:"user_email"`
	// Both are derivable from `items`, but a filter on units is only
	// trustworthy if the number it filtered on is visible next to the row.
	ItemCount     int `json:"item_count"`
	TotalQuantity int `json:"total_quantity"`
}

// statusParams collects requested statuses, accepting a repeated parameter,
// a comma-separated value, or the plural spelling -- the same forms the
// category filter takes, because callers reach for all three.
func statusParams(q url.Values) ([]string, bool) {
	seen := map[string]bool{}
	out := []string{}
	for _, key := range []string{"status", "statuses"} {
		for _, raw := range q[key] {
			for _, part := range strings.Split(raw, ",") {
				part = strings.ToLower(strings.TrimSpace(part))
				if part == "" || seen[part] {
					continue
				}
				if !validStatus(part) {
					return nil, false
				}
				seen[part] = true
				out = append(out, part)
			}
		}
	}
	return out, true
}

// dayParam parses a YYYY-MM-DD boundary. `endOfDay` shifts it to the start of
// the next day so that `to=2026-09-06` includes everything placed that day --
// a filter that silently excludes its own end date is a bug report waiting to
// happen.
func dayParam(raw string, endOfDay bool) (*time.Time, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil, nil
	}
	d, err := time.ParseInLocation("2006-01-02", raw, time.UTC)
	if err != nil {
		return nil, err
	}
	if endOfDay {
		d = d.AddDate(0, 0, 1)
	}
	return &d, nil
}

func (s *Server) AdminOrders(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	limit, err := intParam(q.Get("limit"), defaultAdminLimit, 1, maxAdminLimit)
	if err != nil {
		writeError(w, http.StatusBadRequest, CodeInvalidRequest, "limit is out of range.")
		return
	}
	offset, err := intParam(q.Get("offset"), 0, 0, 1<<30)
	if err != nil {
		writeError(w, http.StatusBadRequest, CodeInvalidRequest, "offset is out of range.")
		return
	}
	statuses, ok := statusParams(q)
	if !ok {
		writeError(w, http.StatusBadRequest, CodeInvalidRequest,
			"status must be pending, confirmed, or cancelled.")
		return
	}

	filter := store.OrderFilter{
		Query:    strings.TrimSpace(q.Get("q")),
		Statuses: statuses,
		Limit:    limit,
		Offset:   offset,
	}

	for _, p := range []struct {
		key  string
		dest **int
	}{
		{"min_total", &filter.MinTotalJPY},
		{"max_total", &filter.MaxTotalJPY},
		{"min_quantity", &filter.MinQuantity},
		{"max_quantity", &filter.MaxQuantity},
	} {
		v, err := optionalInt(q.Get(p.key))
		if err != nil {
			writeError(w, http.StatusBadRequest, CodeInvalidRequest,
				p.key+" must be a non-negative integer.")
			return
		}
		*p.dest = v
	}

	// `days` is shorthand for "the last N days", which is how a person asks.
	// An explicit from/to wins, so the two can never quietly disagree.
	if raw := strings.TrimSpace(q.Get("days")); raw != "" && q.Get("from") == "" {
		days, err := intParam(raw, 0, 1, 3650)
		if err != nil {
			writeError(w, http.StatusBadRequest, CodeInvalidRequest,
				"days must be between 1 and 3650.")
			return
		}
		from := time.Now().UTC().AddDate(0, 0, -days).Truncate(24 * time.Hour)
		filter.From = &from
	}
	if filter.From == nil {
		if filter.From, err = dayParam(q.Get("from"), false); err != nil {
			writeError(w, http.StatusBadRequest, CodeInvalidRequest,
				"from must be a date as YYYY-MM-DD.")
			return
		}
	}
	if filter.To, err = dayParam(q.Get("to"), true); err != nil {
		writeError(w, http.StatusBadRequest, CodeInvalidRequest,
			"to must be a date as YYYY-MM-DD.")
		return
	}

	orders, total, err := s.store.AllOrders(r.Context(), filter)
	if err != nil {
		writeInternal(w, "admin orders", err)
		return
	}
	out := make([]adminOrderJSON, 0, len(orders))
	for _, o := range orders {
		units := 0
		for _, it := range o.Items {
			units += it.Quantity
		}
		out = append(out, adminOrderJSON{
			orderJSON:     toOrder(o.Order),
			UserID:        o.UserID,
			UserName:      o.UserName,
			UserEmail:     o.UserEmail,
			ItemCount:     len(o.Items),
			TotalQuantity: units,
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"orders": out, "total": total, "limit": limit, "offset": offset,
		// Echoed so a consumer can render the filters actually in force rather
		// than the ones it believes it sent.
		"applied": appliedJSON(filter),
	})
}

// appliedJSON reports the filter as the server understood it. Omitted keys
// mean "not filtered", so a View can render the active filters without
// re-deriving them from its own request.
func appliedJSON(f store.OrderFilter) map[string]any {
	applied := map[string]any{"statuses": f.Statuses}
	if f.Statuses == nil {
		applied["statuses"] = []string{}
	}
	if f.Query != "" {
		applied["q"] = f.Query
	}
	if f.MinTotalJPY != nil {
		applied["min_total"] = *f.MinTotalJPY
	}
	if f.MaxTotalJPY != nil {
		applied["max_total"] = *f.MaxTotalJPY
	}
	if f.MinQuantity != nil {
		applied["min_quantity"] = *f.MinQuantity
	}
	if f.MaxQuantity != nil {
		applied["max_quantity"] = *f.MaxQuantity
	}
	if f.From != nil {
		applied["from"] = f.From.Format("2006-01-02")
	}
	if f.To != nil {
		// Reported as the inclusive day the caller asked for, not the
		// exclusive boundary used in SQL.
		applied["to"] = f.To.AddDate(0, 0, -1).Format("2006-01-02")
	}
	return applied
}

type updateOrderStatusRequest struct {
	Status string `json:"status"`
}

func validStatus(s string) bool {
	return s == "pending" || s == "confirmed" || s == "cancelled"
}

func (s *Server) AdminUpdateOrder(w http.ResponseWriter, r *http.Request) {
	var req updateOrderStatusRequest
	if !decodeJSON(w, r, &req) {
		return
	}
	if !validStatus(req.Status) {
		writeError(w, http.StatusBadRequest, CodeInvalidRequest,
			"status must be pending, confirmed, or cancelled.")
		return
	}
	number := r.PathValue("order_number")
	if err := s.store.UpdateOrderStatus(r.Context(), number, req.Status); err != nil {
		if errors.Is(err, store.ErrOrderNotFound) {
			writeError(w, http.StatusNotFound, CodeOrderNotFound, "Order "+number+" was not found.")
			return
		}
		writeInternal(w, "update order status", err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"order_number": number, "status": req.Status})
}

type adminUserJSON struct {
	ID        int64  `json:"id"`
	Name      string `json:"name"`
	Email     string `json:"email"`
	CreatedAt string `json:"created_at"`
	IsAdmin   bool   `json:"is_admin"`
	CartLines int    `json:"cart_lines"`
	Orders    int    `json:"orders"`
	SpentJPY  int    `json:"spent_jpy"`
}

func (s *Server) AdminUsers(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	limit, err := intParam(q.Get("limit"), defaultAdminLimit, 1, maxAdminLimit)
	if err != nil {
		writeError(w, http.StatusBadRequest, CodeInvalidRequest, "limit is out of range.")
		return
	}
	offset, err := intParam(q.Get("offset"), 0, 0, 1<<30)
	if err != nil {
		writeError(w, http.StatusBadRequest, CodeInvalidRequest, "offset is out of range.")
		return
	}
	role := strings.ToLower(strings.TrimSpace(q.Get("role")))
	if role != "" && role != "admin" && role != "customer" {
		writeError(w, http.StatusBadRequest, CodeInvalidRequest,
			"role must be admin or customer.")
		return
	}

	filter := store.UserFilter{
		Query:   strings.TrimSpace(q.Get("q")),
		Role:    role,
		HasCart: q.Get("has_cart") == "true",
		Limit:   limit,
		Offset:  offset,
	}
	for _, p := range []struct {
		key  string
		dest **int
	}{
		{"min_orders", &filter.MinOrders},
		{"max_orders", &filter.MaxOrders},
		{"min_spent", &filter.MinSpentJPY},
		{"max_spent", &filter.MaxSpentJPY},
	} {
		v, err := optionalInt(q.Get(p.key))
		if err != nil {
			writeError(w, http.StatusBadRequest, CodeInvalidRequest,
				p.key+" must be a non-negative integer.")
			return
		}
		*p.dest = v
	}
	if filter.From, err = dayParam(q.Get("from"), false); err != nil {
		writeError(w, http.StatusBadRequest, CodeInvalidRequest,
			"from must be a date as YYYY-MM-DD.")
		return
	}
	if filter.To, err = dayParam(q.Get("to"), true); err != nil {
		writeError(w, http.StatusBadRequest, CodeInvalidRequest,
			"to must be a date as YYYY-MM-DD.")
		return
	}

	users, total, err := s.store.AllUsers(r.Context(), filter)
	if err != nil {
		writeInternal(w, "admin users", err)
		return
	}
	out := make([]adminUserJSON, 0, len(users))
	for _, u := range users {
		out = append(out, adminUserJSON{
			ID: u.ID, Name: u.Name, Email: u.Email,
			CreatedAt: u.CreatedAt.UTC().Format(time.RFC3339),
			IsAdmin:   u.IsAdmin,
			CartLines: u.CartLines, Orders: u.Orders, SpentJPY: u.SpentJPY,
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"users": out, "total": total, "limit": limit, "offset": offset,
		// Same contract as the order list: the View renders the filters in
		// force rather than the ones it believes it sent.
		"applied": appliedUserJSON(filter),
	})
}

// AdminProducts lists products including deactivated ones, which the shop
// endpoint deliberately hides.
func (s *Server) AdminProducts(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	// Grouped by category, like GET /api/v1/products: a consumer renders one
	// section per category without regrouping client-side. Descriptions are
	// included here (the shop endpoint omits them) because admin views show them.
	// maxCatalogLimit stands in for "no cap" -- the store caps rows well below it.
	s.catalogResponse(w, r, store.ProductFilter{
		Query:           strings.TrimSpace(q.Get("q")),
		IncludeInactive: q.Get("include_inactive") != "false",
	}, categoryParams(q), maxCatalogLimit, 0, true)
}

type updateProductRequest struct {
	Name         *string `json:"name"`
	Description  *string `json:"description"`
	BasePriceJPY *int    `json:"base_price_jpy"`
	IsActive     *bool   `json:"is_active"`
}

func (s *Server) AdminUpdateProduct(w http.ResponseWriter, r *http.Request) {
	id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
	if err != nil {
		writeError(w, http.StatusBadRequest, CodeInvalidRequest, "Product id must be an integer.")
		return
	}
	var req updateProductRequest
	if !decodeJSON(w, r, &req) {
		return
	}
	if req.Name != nil && strings.TrimSpace(*req.Name) == "" {
		writeError(w, http.StatusBadRequest, CodeInvalidRequest, "name cannot be blank.")
		return
	}
	if req.BasePriceJPY != nil && (*req.BasePriceJPY < 0 || *req.BasePriceJPY > maxMoneyJPY) {
		writeError(w, http.StatusBadRequest, CodeInvalidRequest, "base_price_jpy is out of range.")
		return
	}

	err = s.store.UpdateProduct(r.Context(), id, store.ProductUpdate{
		Name: req.Name, Description: req.Description,
		BasePriceJPY: req.BasePriceJPY, IsActive: req.IsActive,
	})
	switch {
	case errors.Is(err, store.ErrNothingToUpdate):
		writeError(w, http.StatusBadRequest, CodeInvalidRequest, "No fields to update.")
		return
	case errors.Is(err, store.ErrNotFound):
		writeError(w, http.StatusNotFound, CodeProductNotFound,
			"Product "+strconv.FormatInt(id, 10)+" does not exist.")
		return
	case err != nil:
		writeInternal(w, "update product", err)
		return
	}
	product, err := s.store.Product(r.Context(), id)
	if err != nil {
		// Deactivating hides the product from the read path, so there is
		// nothing to echo back; the update still succeeded.
		writeJSON(w, http.StatusOK, map[string]any{"id": id, "updated": true})
		return
	}
	writeJSON(w, http.StatusOK, toProduct(*product, true))
}

type updateSizeRequest struct {
	SizeName           *string `json:"size_name"`
	PriceAdjustmentJPY *int    `json:"price_adjustment_jpy"`
}

func (s *Server) AdminUpdateSize(w http.ResponseWriter, r *http.Request) {
	id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
	if err != nil {
		writeError(w, http.StatusBadRequest, CodeInvalidRequest, "Size id must be an integer.")
		return
	}
	var req updateSizeRequest
	if !decodeJSON(w, r, &req) {
		return
	}
	err = s.store.UpdateSize(r.Context(), id, store.SizeUpdate{
		SizeName: req.SizeName, PriceAdjustmentJPY: req.PriceAdjustmentJPY,
	})
	switch {
	case errors.Is(err, store.ErrNothingToUpdate):
		writeError(w, http.StatusBadRequest, CodeInvalidRequest, "No fields to update.")
		return
	case errors.Is(err, store.ErrSizeNotFound):
		writeError(w, http.StatusNotFound, CodeSizeNotFound,
			"Size "+strconv.FormatInt(id, 10)+" does not exist.")
		return
	case err != nil:
		writeInternal(w, "update size", err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"id": id, "updated": true})
}

func (s *Server) AdminDeleteProduct(w http.ResponseWriter, r *http.Request) {
	id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
	if err != nil {
		writeError(w, http.StatusBadRequest, CodeInvalidRequest, "Product id must be an integer.")
		return
	}
	err = s.store.DeleteProduct(r.Context(), id)
	switch {
	case errors.Is(err, store.ErrNotFound):
		writeError(w, http.StatusNotFound, CodeProductNotFound,
			"Product "+strconv.FormatInt(id, 10)+" does not exist.")
		return
	case errors.Is(err, store.ErrProductInUse):
		writeError(w, http.StatusConflict, CodeInvalidRequest,
			"Product "+strconv.FormatInt(id, 10)+" appears in an order; deactivate it instead.")
		return
	case err != nil:
		writeInternal(w, "delete product", err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func appliedUserJSON(f store.UserFilter) map[string]any {
	applied := map[string]any{}
	if f.Query != "" {
		applied["q"] = f.Query
	}
	if f.Role != "" {
		applied["role"] = f.Role
	}
	if f.HasCart {
		applied["has_cart"] = true
	}
	for key, value := range map[string]*int{
		"min_orders": f.MinOrders, "max_orders": f.MaxOrders,
		"min_spent": f.MinSpentJPY, "max_spent": f.MaxSpentJPY,
	} {
		if value != nil {
			applied[key] = *value
		}
	}
	if f.From != nil {
		applied["from"] = f.From.Format("2006-01-02")
	}
	if f.To != nil {
		applied["to"] = f.To.AddDate(0, 0, -1).Format("2006-01-02")
	}
	return applied
}
