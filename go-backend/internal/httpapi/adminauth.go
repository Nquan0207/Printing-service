package httpapi

import (
	"log/slog"
	"net/http"
)

// requireAdmin gates /api/v1/admin/*.
//
// Identity still comes from X-Stockroom-User, which this service trusts
// without verification -- so this is an *authorization* check, not
// authentication. It stops a non-admin user of the shop from reaching admin
// routes; it does not stop someone who can already forge the header. That
// remains true only while the port is loopback-bound.
//
// The admin flag is read from the database per request, so revoking it takes
// effect immediately rather than at the next restart.
func (s *Server) requireAdmin(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		userID := s.currentUserID(r)
		isAdmin, err := s.store.IsAdmin(r.Context(), userID)
		if err != nil {
			writeInternal(w, "check admin", err)
			return
		}
		if !isAdmin {
			slog.Warn("admin route refused", "user_id", userID, "path", r.URL.Path)
			writeError(w, http.StatusForbidden, CodeForbidden,
				"This endpoint requires an administrator account.")
			return
		}
		next(w, r)
	}
}
