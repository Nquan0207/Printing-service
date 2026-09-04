package httpapi

import (
	"net/http"

	"github.com/octguy/stockroom/internal/media"
	"github.com/octguy/stockroom/internal/store"
)

type Server struct {
	store *store.Store
	media *media.Store
}

func New(s *store.Store, m *media.Store) *Server {
	return &Server{store: s, media: m}
}

// Routes builds the mux. Go 1.22+ patterns carry the method, and the
// `{key...}` wildcard on /media matches image keys containing slashes --
// a plain {key} would not.
func (s *Server) Routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", s.Health)
	mux.HandleFunc("GET /api/v1/categories", s.ListCategories)
	mux.HandleFunc("GET /api/v1/products", s.SearchProducts)
	mux.HandleFunc("GET /api/v1/products/{id}", s.GetProduct)
	mux.HandleFunc("POST /api/v1/quote", s.CreateQuote)
	mux.HandleFunc("GET /media/{key...}", s.Media)
	return mux
}
