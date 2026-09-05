package httpapi

import (
	"encoding/json"
	"log/slog"
	"net/http"
)

// Error codes from docs/api-contract.yaml. Callers write one error path, so
// every non-2xx response uses this envelope without exception.
const (
	CodeInvalidRequest   = "invalid_request"
	CodeProductNotFound  = "product_not_found"
	CodeSizeNotFound     = "size_not_found"
	CodeCartEmpty        = "cart_empty"
	CodeCartItemNotFound = "cart_item_not_found"
	CodeOrderNotFound    = "order_not_found"
	CodeForbidden        = "forbidden"
	CodeInternal         = "internal"
)

type errorBody struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

type errorEnvelope struct {
	Error errorBody `json:"error"`
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(payload); err != nil {
		// The status line is already sent; all we can do is record it.
		slog.Error("encode response", "err", err)
	}
}

func writeError(w http.ResponseWriter, status int, code, message string) {
	writeJSON(w, status, errorEnvelope{errorBody{Code: code, Message: message}})
}

// writeInternal logs the cause and returns a generic message: internal detail
// is never leaked to the caller.
func writeInternal(w http.ResponseWriter, op string, err error) {
	slog.Error("request failed", "op", op, "err", err)
	writeError(w, http.StatusInternalServerError, CodeInternal, "Internal error.")
}
