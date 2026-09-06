package httpapi

import (
	"net/http"
	"strconv"
	"strings"
)

// corsMaxAge caps how long a browser may cache a preflight result.
const corsMaxAge = 600

// withCORS answers cross-origin requests.
//
// The default origin is "*", which is safe ONLY because the service is
// loopback-bound. Identity here is an unverified X-Stockroom-User header, so a
// reachable origin-wildcarded API lets any page the user visits call it and
// act as any user -- including an admin. Narrow STOCKROOM_CORS_ORIGIN before
// this is ever exposed.
func withCORS(origin string, next http.Handler) http.Handler {
	allowHeaders := strings.Join([]string{"Content-Type", "Accept", UserHeader}, ", ")
	allowMethods := "GET, POST, PATCH, DELETE, OPTIONS"

	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requestOrigin := r.Header.Get("Origin")
		if requestOrigin != "" {
			if origin == "*" {
				w.Header().Set("Access-Control-Allow-Origin", "*")
			} else if origin == requestOrigin {
				w.Header().Set("Access-Control-Allow-Origin", origin)
				// Tell caches the response varies by origin, otherwise a proxy
				// may serve one origin's response to another.
				w.Header().Add("Vary", "Origin")
			}
		}

		if r.Method == http.MethodOptions && r.Header.Get("Access-Control-Request-Method") != "" {
			w.Header().Set("Access-Control-Allow-Methods", allowMethods)
			w.Header().Set("Access-Control-Allow-Headers", allowHeaders)
			w.Header().Set("Access-Control-Max-Age", strconv.Itoa(corsMaxAge))
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}
