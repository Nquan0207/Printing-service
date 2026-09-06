package httpapi

import (
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strconv"

	"github.com/octguy/stockroom/internal/store"
)

// maxMoneyJPY is the ceiling for any yen figure we compute. schema.sql stores
// money in INTEGER columns (subtotal_jpy, total_jpy), so a value past int32
// would be rejected by Postgres at order time. Catching it at the quote keeps
// the failure early and legible instead of surfacing as a 500 on checkout.
const maxMoneyJPY = 2147483647

// maxRequestBody bounds JSON bodies; every request shape here is tiny.
const maxRequestBody = 64 << 10

type quoteRequest struct {
	ProductID int64 `json:"product_id"`
	SizeID    int64 `json:"size_id"`
	Quantity  int   `json:"quantity"`
}

type quoteResponse struct {
	ProductID    int64    `json:"product_id"`
	ProductName  string   `json:"product_name"`
	SizeID       int64    `json:"size_id"`
	SizeName     string   `json:"size_name"`
	Quantity     int      `json:"quantity"`
	UnitPriceJPY int      `json:"unit_price_jpy"`
	SubtotalJPY  int      `json:"subtotal_jpy"`
	Currency     string   `json:"currency"`
	Notes        []string `json:"notes"`
}

// decodeJSON reads a bounded, strictly-typed JSON body. Unknown fields are
// rejected so a typo in a tool argument fails loudly rather than silently
// doing the wrong thing.
func decodeJSON(w http.ResponseWriter, r *http.Request, dst any) bool {
	decoder := json.NewDecoder(io.LimitReader(r.Body, maxRequestBody))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(dst); err != nil {
		writeError(w, http.StatusBadRequest, CodeInvalidRequest, "Request body must be valid JSON matching the documented shape.")
		return false
	}
	return true
}

func (s *Server) CreateQuote(w http.ResponseWriter, r *http.Request) {
	var req quoteRequest
	if !decodeJSON(w, r, &req) {
		return
	}
	if req.Quantity < 1 {
		writeError(w, http.StatusBadRequest, CodeInvalidRequest, "quantity must be at least 1.")
		return
	}

	priced, err := s.store.PricedSize(r.Context(), req.ProductID, req.SizeID)
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
		writeInternal(w, "price size", err)
		return
	}

	subtotal, ok := subtotalJPY(priced.UnitPriceJPY, req.Quantity)
	if !ok {
		writeError(w, http.StatusBadRequest, CodeInvalidRequest,
			"quantity is too large: the subtotal would exceed the maximum storable amount.")
		return
	}

	writeJSON(w, http.StatusOK, quoteResponse{
		ProductID:    priced.ProductID,
		ProductName:  priced.ProductName,
		SizeID:       priced.SizeID,
		SizeName:     priced.SizeName,
		Quantity:     req.Quantity,
		UnitPriceJPY: priced.UnitPriceJPY,
		SubtotalJPY:  subtotal,
		Currency:     "JPY",
		// Stated outright so a model cannot present this as a real quote: the
		// source site prices in quantity tiers, but the schema keeps one price
		// per size.
		Notes: []string{"Mock pricing: no tax, shipping, or quantity discounts."},
	})
}

// subtotalJPY multiplies without overflowing the int32 the schema stores.
func subtotalJPY(unitPrice, quantity int) (int, bool) {
	if unitPrice < 0 || quantity < 1 {
		return 0, false
	}
	if unitPrice != 0 && quantity > maxMoneyJPY/unitPrice {
		return 0, false
	}
	return unitPrice * quantity, true
}
