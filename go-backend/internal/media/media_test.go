package media

import (
	"context"
	"errors"
	"io"
	"os"
	"testing"

	"github.com/octguy/stockroom/internal/config"
)

// The key arrives straight from a URL path, so traversal and root-addressing
// attempts must be rejected before they reach MinIO.
func TestValidKey(t *testing.T) {
	valid := []string{
		"products/158/abc.jpg",
		"products/1/2/3/deep.png",
		"single.jpg",
	}
	for _, key := range valid {
		if !ValidKey(key) {
			t.Errorf("ValidKey(%q) = false, want true", key)
		}
	}

	invalid := []string{
		"",                      // bucket root
		"/products/abc.jpg",     // absolute
		"../secrets.txt",        // traversal
		"products/../../etc/pw", // traversal, nested
		"products/./abc.jpg",    // current-dir segment
		"products//abc.jpg",     // empty segment
		"products/",             // trailing empty segment
	}
	for _, key := range invalid {
		if ValidKey(key) {
			t.Errorf("ValidKey(%q) = true, want false", key)
		}
	}
}

func testStore(t *testing.T) *Store {
	t.Helper()
	if os.Getenv("STOCKROOM_TEST_MINIO") == "" {
		t.Skip("set STOCKROOM_TEST_MINIO=1 to run MinIO integration tests")
	}
	s, err := New(config.MinIO{
		Endpoint:  envOr("MINIO_ENDPOINT", "127.0.0.1:9000"),
		AccessKey: envOr("MINIO_ACCESS_KEY", "minioadmin"),
		SecretKey: envOr("MINIO_SECRET_KEY", "minioadmin"),
		Bucket:    envOr("MINIO_BUCKET", "stockroom-media"),
	})
	if err != nil {
		t.Fatalf("connect minio: %v", err)
	}
	return s
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func TestPingReachesTheBucket(t *testing.T) {
	if err := testStore(t).Ping(context.Background()); err != nil {
		t.Errorf("Ping() = %v, want nil", err)
	}
}

func TestGetMissingKeyIsNotFound(t *testing.T) {
	_, err := testStore(t).Get(context.Background(), "products/does-not-exist/nope.jpg")
	if !errors.Is(err, ErrNotFound) {
		t.Errorf("Get(missing) = %v, want ErrNotFound", err)
	}
}

func TestGetRejectsTraversalBeforeCallingMinIO(t *testing.T) {
	_, err := testStore(t).Get(context.Background(), "../../etc/passwd")
	if !errors.Is(err, ErrBadKey) {
		t.Errorf("Get(traversal) = %v, want ErrBadKey", err)
	}
}

// STOCKROOM_TEST_MEDIA_KEY should name a real object; the crawler writes keys
// like products/158/<sha>.jpg.
func TestGetStreamsRealObject(t *testing.T) {
	key := os.Getenv("STOCKROOM_TEST_MEDIA_KEY")
	if key == "" {
		t.Skip("set STOCKROOM_TEST_MEDIA_KEY to a real object key")
	}
	object, err := testStore(t).Get(context.Background(), key)
	if err != nil {
		t.Fatalf("Get(%q) = %v", key, err)
	}
	defer object.Body.Close()

	body, err := io.ReadAll(object.Body)
	if err != nil {
		t.Fatal(err)
	}
	if int64(len(body)) != object.Size {
		t.Errorf("read %d bytes, Size reported %d", len(body), object.Size)
	}
	if object.ContentType == "" {
		t.Error("ContentType is empty; the proxy would send no Content-Type")
	}
}
