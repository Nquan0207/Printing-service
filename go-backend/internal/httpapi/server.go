package httpapi

import (
	"net/http"

	"github.com/octguy/stockroom/internal/media"
	"github.com/octguy/stockroom/internal/store"
)

type Server struct {
	store *store.Store
	media *media.Store
	// defaultUserID answers requests that carry no X-Stockroom-User header,
	// e.g. from Claude or ChatGPT, which never call login.
	defaultUserID int64
}

func New(s *store.Store, m *media.Store, defaultUserID int64) *Server {
	return &Server{store: s, media: m, defaultUserID: defaultUserID}
}

// Routes builds the mux. Go 1.22+ patterns carry the method, and the
// `{key...}` wildcard on /media matches image keys containing slashes --
// a plain {key} would not.
func (s *Server) Routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", s.Health)
	mux.HandleFunc("POST /api/v1/login", s.Login)
	mux.HandleFunc("GET /api/v1/categories", s.ListCategories)
	mux.HandleFunc("GET /api/v1/products", s.SearchProducts)
	mux.HandleFunc("GET /api/v1/products/{id}", s.GetProduct)
	mux.HandleFunc("POST /api/v1/quote", s.CreateQuote)
	mux.HandleFunc("GET /api/v1/cart", s.GetCart)
	mux.HandleFunc("POST /api/v1/cart/items", s.AddCartItem)
	mux.HandleFunc("DELETE /api/v1/cart/items/{item_id}", s.DeleteCartItem)
	mux.HandleFunc("POST /api/v1/orders", s.PlaceOrder)
	mux.HandleFunc("GET /api/v1/orders/{order_number}", s.GetOrder)
	mux.HandleFunc("GET /media/{key...}", s.Media)
	return mux
}
