package httpapi

import (
	"errors"
	"net/http"
	"strings"
	"time"

	"github.com/octguy/stockroom/internal/store"
)

type placeOrderRequest struct {
	ShippingAddress string `json:"shipping_address"`
}

type orderItemJSON struct {
	ProductID    *int64 `json:"product_id"`
	ProductName  string `json:"product_name"`
	SizeName     string `json:"size_name"`
	Quantity     int    `json:"quantity"`
	UnitPriceJPY int    `json:"unit_price_jpy"`
	SubtotalJPY  int    `json:"subtotal_jpy"`
}

type orderJSON struct {
	OrderNumber     string          `json:"order_number"`
	Status          string          `json:"status"`
	ShippingAddress string          `json:"shipping_address"`
	TotalJPY        int             `json:"total_jpy"`
	Items           []orderItemJSON `json:"items"`
	CreatedAt       string          `json:"created_at"`
}

func toOrder(o store.Order) orderJSON {
	items := make([]orderItemJSON, 0, len(o.Items))
	for _, it := range o.Items {
		items = append(items, orderItemJSON{
			ProductID:    it.ProductID,
			ProductName:  it.ProductName,
			SizeName:     it.SizeName,
			Quantity:     it.Quantity,
			UnitPriceJPY: it.UnitPriceJPY,
			SubtotalJPY:  it.SubtotalJPY,
		})
	}
	return orderJSON{
		OrderNumber:     o.OrderNumber,
		Status:          o.Status,
		ShippingAddress: o.ShippingAddress,
		TotalJPY:        o.TotalJPY,
		Items:           items,
		CreatedAt:       o.CreatedAt.UTC().Format(time.RFC3339),
	}
}

// PlaceOrder converts the cart into an order.
//
// The confirm-gate is NOT enforced here: this endpoint cannot see which View
// called it, so the MCP server must ensure place_order is reachable only from
// the confirm View. See docs/api-contract.md.
// ListOrders returns the caller's own order history.
//
// Scoped to currentUserID like every other shopper route -- there is no way to
// ask for somebody else's, because no user id is accepted from the request
// body or query string.
func (s *Server) ListOrders(w http.ResponseWriter, r *http.Request) {
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

	orders, total, err := s.store.UserOrders(r.Context(), s.currentUserID(r), limit, offset)
	if err != nil {
		writeInternal(w, "list orders", err)
		return
	}
	out := make([]orderJSON, 0, len(orders))
	for _, o := range orders {
		out = append(out, toOrder(o))
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"orders": out, "total": total, "limit": limit, "offset": offset,
	})
}

func (s *Server) PlaceOrder(w http.ResponseWriter, r *http.Request) {
	var req placeOrderRequest
	if !decodeJSON(w, r, &req) {
		return
	}
	address := strings.TrimSpace(req.ShippingAddress)
	if address == "" {
		writeError(w, http.StatusBadRequest, CodeInvalidRequest, "shipping_address is required.")
		return
	}

	order, err := s.store.PlaceOrder(r.Context(), s.currentUserID(r), address)
	switch {
	case errors.Is(err, store.ErrCartEmpty):
		writeError(w, http.StatusConflict, CodeCartEmpty, "The cart is empty.")
		return
	case errors.Is(err, store.ErrOrderTooLarge):
		writeError(w, http.StatusBadRequest, CodeInvalidRequest,
			"The cart total exceeds the maximum storable amount.")
		return
	case err != nil:
		writeInternal(w, "place order", err)
		return
	}
	writeJSON(w, http.StatusCreated, toOrder(order))
}

func (s *Server) GetOrder(w http.ResponseWriter, r *http.Request) {
	number := r.PathValue("order_number")
	order, err := s.store.Order(r.Context(), s.currentUserID(r), number)
	if errors.Is(err, store.ErrOrderNotFound) {
		writeError(w, http.StatusNotFound, CodeOrderNotFound,
			"Order "+number+" was not found.")
		return
	}
	if err != nil {
		writeInternal(w, "get order", err)
		return
	}
	writeJSON(w, http.StatusOK, toOrder(order))
}
