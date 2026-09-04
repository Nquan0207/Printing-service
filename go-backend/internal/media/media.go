// Package media reads product images from MinIO.
//
// The bucket has no public policy: this service is its only reader, and it
// exposes objects solely through GET /media/{key}. Image keys never leave the
// database as URLs.
package media

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"

	"github.com/octguy/stockroom/internal/config"
)

var (
	ErrNotFound = errors.New("object not found")
	ErrBadKey   = errors.New("invalid object key")
)

// Object is a streaming handle to one stored image. Body must be closed.
type Object struct {
	Body        io.ReadCloser
	ContentType string
	Size        int64
	ETag        string
}

type Store struct {
	client *minio.Client
	bucket string
}

func New(cfg config.MinIO) (*Store, error) {
	client, err := minio.New(cfg.Endpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(cfg.AccessKey, cfg.SecretKey, ""),
		Secure: cfg.Secure,
	})
	if err != nil {
		return nil, fmt.Errorf("connect minio: %w", err)
	}
	return &Store{client: client, bucket: cfg.Bucket}, nil
}

// ValidKey rejects keys that could escape the intended prefix or address the
// bucket root. The key arrives from a URL path, so it is caller-controlled.
func ValidKey(key string) bool {
	if key == "" || strings.HasPrefix(key, "/") || strings.Contains(key, "//") {
		return false
	}
	for _, segment := range strings.Split(key, "/") {
		if segment == "" || segment == "." || segment == ".." {
			return false
		}
	}
	return true
}

// Get streams one object. The caller must close Object.Body.
func (s *Store) Get(ctx context.Context, key string) (*Object, error) {
	if !ValidKey(key) {
		return nil, ErrBadKey
	}
	obj, err := s.client.GetObject(ctx, s.bucket, key, minio.GetObjectOptions{})
	if err != nil {
		return nil, fmt.Errorf("get object %s: %w", key, err)
	}
	// GetObject is lazy: the request only happens on Stat, so this is where a
	// missing key surfaces.
	info, err := obj.Stat()
	if err != nil {
		obj.Close()
		if minio.ToErrorResponse(err).StatusCode == http.StatusNotFound {
			return nil, ErrNotFound
		}
		return nil, fmt.Errorf("stat object %s: %w", key, err)
	}
	return &Object{
		Body:        obj,
		ContentType: info.ContentType,
		Size:        info.Size,
		ETag:        info.ETag,
	}, nil
}

// Ping reports whether the bucket is reachable right now, for /healthz.
func (s *Store) Ping(ctx context.Context) error {
	exists, err := s.client.BucketExists(ctx, s.bucket)
	if err != nil {
		return fmt.Errorf("stat bucket %s: %w", s.bucket, err)
	}
	if !exists {
		return fmt.Errorf("bucket %s does not exist", s.bucket)
	}
	return nil
}
