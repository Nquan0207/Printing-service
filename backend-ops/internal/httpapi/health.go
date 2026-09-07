package httpapi

import (
	"context"
	"net/http"
	"time"
)

type healthResponse struct {
	Status   string `json:"status"`
	Database string `json:"database"`
	MinIO    string `json:"minio"`
}

// Health checks both dependencies and returns 503 if either is down, so a
// silently unavailable Postgres or MinIO surfaces immediately.
func (s *Server) Health(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
	defer cancel()

	body := healthResponse{Status: "ok", Database: "ok", MinIO: "ok"}
	status := http.StatusOK

	if err := s.store.Ping(ctx); err != nil {
		body.Database, body.Status, status = "down", "degraded", http.StatusServiceUnavailable
	}
	if err := s.media.Ping(ctx); err != nil {
		body.MinIO, body.Status, status = "down", "degraded", http.StatusServiceUnavailable
	}
	writeJSON(w, status, body)
}
