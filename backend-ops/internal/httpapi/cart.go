package httpapi

import (
	"errors"
	"net/http"
	"strconv"

	"github.com/octguy/stockroom/internal/store"
)

type cartSizeJSON struct {
	ID           int64  `json:"id"`
	SizeName     string `json:"size_name"`
	UnitPriceJPY int    `json:"unit_price_jpy"`
}

type cartItemJSON struct {
	ID          int64   `json:"id"`
	ProductID   int64   `json:"product_id"`
	ProductName string  `json:"product_name"`
	SizeID      int64   `json:"size_id"`
	SizeName    string  `json:"size_name"`
	Image       *string `json:"image"`
	Quantity    int     `json:"quantity"`
	// Every size this product offers, so a client can switch size on the line
	// without fetching the product again. Ordered cheapest first.
	Sizes        []cartSizeJSON `json:"sizes"`
	UnitPriceJPY int            `json:"unit_price_jpy"`
	SubtotalJPY  int            `json:"subtotal_jpy"`
}

type cartJSON struct {
	Items     []cartItemJSON `json:"items"`
	ItemCount int            `json:"item_count"`
	TotalJPY  int            `json:"total_jpy"`
}

type addCartItemRequest struct {
	ProductID int64 `json:"product_id"`
	SizeID    int64 `json:"size_id"`
	Quantity  int   `json:"quantity"`
}

type updateCartItemRequest struct {
	SizeID   int64 `json:"size_id"`
	Quantity int   `json:"quantity"`
}

func toCart(c store.Cart) cartJSON {
	items := make([]cartItemJSON, 0, len(c.Items))
	for _, it := range c.Items {
		var image *string
		if it.ImageKey != nil {
			path := "/media/" + *it.ImageKey
			image = &path
		}
		sizes := make([]cartSizeJSON, 0, len(it.Sizes))
		for _, sz := range it.Sizes {
			sizes = append(sizes, cartSizeJSON{
				ID: sz.SizeID, SizeName: sz.SizeName, UnitPriceJPY: sz.UnitPriceJPY,
			})
		}
		items = append(items, cartItemJSON{
			ID:           it.ID,
			ProductID:    it.ProductID,
			ProductName:  it.ProductName,
			SizeID:       it.SizeID,
			SizeName:     it.SizeName,
			Image:        image,
			Quantity:     it.Quantity,
			Sizes:        sizes,
			UnitPriceJPY: it.UnitPriceJPY,
			SubtotalJPY:  it.UnitPriceJPY * it.Quantity,
		})
	}
	return cartJSON{Items: items, ItemCount: len(items), TotalJPY: c.TotalJPY}
}

// writeCart returns the whole cart after every operation, so a View re-renders
// from one response and never recomputes a total.
func (s *Server) writeCart(w http.ResponseWriter, r *http.Request, userID int64) {
	cart, err := s.store.Cart(r.Context(), userID)
	if err != nil {
		writeInternal(w, "read cart", err)
		return
	}
	writeJSON(w, http.StatusOK, toCart(cart))
}

func (s *Server) GetCart(w http.ResponseWriter, r *http.Request) {
	s.writeCart(w, r, s.currentUserID(r))
}

func (s *Server) AddCartItem(w http.ResponseWriter, r *http.Request) {
	var req addCartItemRequest
	if !decodeJSON(w, r, &req) {
		return
	}
	if req.Quantity < 1 {
		writeError(w, http.StatusBadRequest, CodeInvalidRequest, "quantity must be at least 1.")
		return
	}

	userID := s.currentUserID(r)
	err := s.store.AddToCart(r.Context(), userID, req.ProductID, req.SizeID, req.Quantity)
	switch {
	case errors.Is(err, store.ErrNotFound):
		writeError(w, http.StatusNotFound, CodeProductNotFound,
			"Product "+strconv.FormatInt(req.ProductID, 10)+" does not exist.")
		return
	case errors.Is(err, store.ErrSizeNotFound):
		writeError(w, http.StatusNotFound, CodeSizeNotFound,
			"Size "+strconv.FormatInt(req.SizeID, 10)+" is not a size of product "+
				strconv.FormatInt(req.ProductID, 10)+".")
		return
	case err != nil:
		writeInternal(w, "add to cart", err)
		return
	}
	s.writeCart(w, r, userID)
}

// UpdateCartItem changes one line's size and/or quantity and returns the whole
// cart, so the caller re-renders totals from one response rather than
// recomputing them.
func (s *Server) UpdateCartItem(w http.ResponseWriter, r *http.Request) {
	itemID, err := strconv.ParseInt(r.PathValue("item_id"), 10, 64)
	if err != nil {
		writeError(w, http.StatusBadRequest, CodeInvalidRequest, "Cart item id must be an integer.")
		return
	}
	var req updateCartItemRequest
	if !decodeJSON(w, r, &req) {
		return
	}
	if req.Quantity < 1 {
		writeError(w, http.StatusBadRequest, CodeInvalidRequest, "quantity must be at least 1.")
		return
	}
	if req.SizeID <= 0 {
		writeError(w, http.StatusBadRequest, CodeInvalidRequest, "size_id is required.")
		return
	}

	userID := s.currentUserID(r)
	err = s.store.UpdateCartItem(r.Context(), userID, itemID, req.SizeID, req.Quantity)
	switch {
	case errors.Is(err, store.ErrCartItemNotFound):
		writeError(w, http.StatusNotFound, CodeCartItemNotFound,
			"Cart item "+strconv.FormatInt(itemID, 10)+" is not in your cart.")
		return
	case errors.Is(err, store.ErrSizeNotFound):
		writeError(w, http.StatusNotFound, CodeSizeNotFound,
			"Size "+strconv.FormatInt(req.SizeID, 10)+" is not a size of that product.")
		return
	case err != nil:
		writeInternal(w, "update cart item", err)
		return
	}
	s.writeCart(w, r, userID)
}

func (s *Server) DeleteCartItem(w http.ResponseWriter, r *http.Request) {
	itemID, err := strconv.ParseInt(r.PathValue("item_id"), 10, 64)
	if err != nil {
		writeError(w, http.StatusBadRequest, CodeInvalidRequest, "Cart item id must be an integer.")
		return
	}
	userID := s.currentUserID(r)

	// Scoped to the owner: another user's line reads as not found rather than
	// forbidden, so the endpoint cannot be used to probe for its existence.
	if err := s.store.RemoveCartItem(r.Context(), userID, itemID); err != nil {
		if errors.Is(err, store.ErrCartItemNotFound) {
			writeError(w, http.StatusNotFound, CodeCartItemNotFound,
				"Cart item "+strconv.FormatInt(itemID, 10)+" is not in your cart.")
			return
		}
		writeInternal(w, "remove cart item", err)
		return
	}
	s.writeCart(w, r, userID)
}
