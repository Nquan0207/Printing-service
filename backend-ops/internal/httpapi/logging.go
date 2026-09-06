package httpapi

import (
	"log/slog"
	"net/http"
	"strings"
	"time"
)

// statusRecorder captures what the handler wrote, since http.ResponseWriter
// exposes neither the status code nor the byte count after the fact.
type statusRecorder struct {
	http.ResponseWriter
	status int
	bytes  int
}

func (r *statusRecorder) WriteHeader(code int) {
	r.status = code
	r.ResponseWriter.WriteHeader(code)
}

func (r *statusRecorder) Write(b []byte) (int, error) {
	if r.status == 0 {
		r.status = http.StatusOK // handler wrote a body without WriteHeader
	}
	n, err := r.ResponseWriter.Write(b)
	r.bytes += n
	return n, err
}

// Flush keeps streaming responses (the media proxy) working through the wrapper.
func (r *statusRecorder) Flush() {
	if f, ok := r.ResponseWriter.(http.Flusher); ok {
		f.Flush()
	}
}

// withLogging records one line per request: what was called, by whom, how it
// ended and how long it took.
//
// Level reflects the outcome so a tail can be filtered: 5xx is ERROR, 4xx is
// WARN, everything else INFO. /healthz drops to DEBUG when it succeeds --
// Docker probes it every 15s and would otherwise bury real traffic.
func withLogging(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		started := time.Now()
		rec := &statusRecorder{ResponseWriter: w}
		next.ServeHTTP(rec, r)

		if rec.status == 0 {
			rec.status = http.StatusOK
		}
		attrs := []any{
			"method", r.Method,
			"path", r.URL.Path,
			"status", rec.status,
			"dur_ms", time.Since(started).Milliseconds(),
		}
		if q := r.URL.RawQuery; q != "" {
			attrs = append(attrs, "query", q)
		}
		// Who the request claimed to be. Absent means the default user.
		if u := r.Header.Get(UserHeader); u != "" {
			attrs = append(attrs, "user", u)
		}
		if rec.bytes > 0 {
			attrs = append(attrs, "bytes", rec.bytes)
		}

		switch {
		case rec.status >= 500:
			slog.Error("request", attrs...)
		case rec.status >= 400:
			slog.Warn("request", attrs...)
		case r.URL.Path == "/healthz" || strings.HasPrefix(r.URL.Path, "/media/"):
			// Healthchecks and image fetches are high-volume and low-signal.
			slog.Debug("request", attrs...)
		default:
			slog.Info("request", attrs...)
		}
	})
}
