package httpapi

import (
	"errors"
	"net/http"
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
	status := strings.TrimSpace(q.Get("status"))
	if status != "" && !validStatus(status) {
		writeError(w, http.StatusBadRequest, CodeInvalidRequest,
			"status must be pending, confirmed, or cancelled.")
		return
	}

	orders, total, err := s.store.AllOrders(r.Context(), status, limit, offset)
	if err != nil {
		writeInternal(w, "admin orders", err)
		return
	}
	out := make([]adminOrderJSON, 0, len(orders))
	for _, o := range orders {
		out = append(out, adminOrderJSON{
			orderJSON: toOrder(o.Order),
			UserID:    o.UserID,
			UserName:  o.UserName,
			UserEmail: o.UserEmail,
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"orders": out, "total": total, "limit": limit, "offset": offset,
	})
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
	users, total, err := s.store.AllUsers(r.Context(), limit, offset)
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
	})
}

// AdminProducts lists products including deactivated ones, which the shop
// endpoint deliberately hides.
func (s *Server) AdminProducts(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	products, err := s.store.SearchProducts(r.Context(), store.ProductFilter{
		Query:           strings.TrimSpace(q.Get("q")),
		CategorySlugs:   categoryParams(q),
		IncludeInactive: q.Get("include_inactive") != "false",
	})
	if err != nil {
		writeInternal(w, "admin products", err)
		return
	}
	// Grouped by category, like GET /api/v1/products: a consumer renders one
	// section per category without regrouping client-side. Descriptions are
	// included here (the shop endpoint omits them) because admin views show them.
	writeJSON(w, http.StatusOK, groupByCategory(products, len(products), 0, true))
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
