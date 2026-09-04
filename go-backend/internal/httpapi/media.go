package httpapi

import (
	"errors"
	"io"
	"log/slog"
	"net/http"
	"strconv"

	"github.com/octguy/stockroom/internal/media"
)

// Media streams a product image from MinIO. The bucket is private, so this
// proxy is its only reader -- and it is same-origin with the API, which is why
// an iframe sandbox can load the paths that product responses hand out.
func (s *Server) Media(w http.ResponseWriter, r *http.Request) {
	key := r.PathValue("key")

	object, err := s.media.Get(r.Context(), key)
	switch {
	case errors.Is(err, media.ErrNotFound), errors.Is(err, media.ErrBadKey):
		http.NotFound(w, r)
		return
	case err != nil:
		slog.Error("media fetch failed", "key", key, "err", err)
		http.Error(w, "internal error", http.StatusInternalServerError)
		return
	}
	defer object.Body.Close()

	if object.ContentType != "" {
		w.Header().Set("Content-Type", object.ContentType)
	}
	w.Header().Set("Content-Length", strconv.FormatInt(object.Size, 10))
	// Keys are content-addressed by the crawler, so a given key's bytes never
	// change and the response can be cached indefinitely.
	w.Header().Set("Cache-Control", "public, max-age=31536000, immutable")
	if object.ETag != "" {
		w.Header().Set("ETag", `"`+object.ETag+`"`)
	}

	if _, err := io.Copy(w, object.Body); err != nil {
		// Headers are already sent; the client likely went away.
		slog.Warn("media stream interrupted", "key", key, "err", err)
	}
}
