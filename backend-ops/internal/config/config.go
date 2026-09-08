// Package config reads service settings from the environment.
//
// Every value has a default matching the repo's docker-compose.yml, so
// `go run ./cmd/api` works with no setup. Variable names match the ones the
// crawler already uses.
package config

import (
	"os"
	"strconv"
	"strings"
)

type MinIO struct {
	Endpoint  string
	AccessKey string
	SecretKey string
	Bucket    string
	Secure    bool
}

type Config struct {
	// Addr is loopback-only by design: the MCP server is the sole client and
	// the service trusts X-Stockroom-User without verification.
	Addr        string
	DatabaseURL string
	MinIO       MinIO
	// AdminEmails are granted is_admin at startup. Admin is never granted
	// over HTTP, so the admin surface cannot escalate its own access.
	AdminEmails []string
	// ShopEnabled gates the customer-facing home page.
	ShopEnabled bool
	// LogLevel is debug|info|warn|error. debug also surfaces /healthz and
	// /media requests, which are filtered out at info.
	LogLevel string
	// CORSOrigin is the allowed origin, or "*" for any. Wildcard is safe only
	// while the service is loopback-bound -- see withCORS.
	CORSOrigin string
}

func Load() Config {
	return Config{
		Addr:        env("STOCKROOM_ADDR", "127.0.0.1:8080"),
		DatabaseURL: env("STOCKROOM_DATABASE_URL", "postgresql://raksul:raksul_password@127.0.0.1:5432/stockroom"),
		AdminEmails: listEnv("STOCKROOM_ADMIN_EMAILS", "admin@gmail.com"),
		ShopEnabled: boolEnv("SHOP_ENABLED", true),
		LogLevel:    env("STOCKROOM_LOG_LEVEL", "info"),
		CORSOrigin:  env("STOCKROOM_CORS_ORIGIN", "*"),
		MinIO: MinIO{
			Endpoint:  env("MINIO_ENDPOINT", "127.0.0.1:9000"),
			AccessKey: env("MINIO_ACCESS_KEY", "minioadmin"),
			SecretKey: env("MINIO_SECRET_KEY", "minioadmin"),
			Bucket:    env("MINIO_BUCKET", "stockroom-media"),
			Secure:    boolEnv("MINIO_SECURE", false),
		},
	}
}

func env(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func listEnv(key, fallback string) []string {
	raw := env(key, fallback)
	var out []string
	for _, item := range strings.Split(raw, ",") {
		if item = strings.TrimSpace(item); item != "" {
			out = append(out, item)
		}
	}
	return out
}

func boolEnv(key string, fallback bool) bool {
	v, err := strconv.ParseBool(os.Getenv(key))
	if err != nil {
		return fallback
	}
	return v
}
