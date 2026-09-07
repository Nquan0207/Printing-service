package httpapi

import "net/http"

// PublicConfig tells the frontend how the server is configured. The shop
// toggle lives server-side rather than in the SPA's build so it can be flipped
// with an env var and a restart, without rebuilding the frontend.
func (s *Server) PublicConfig(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{
		"shop_enabled": s.shopEnabled,
	})
}
