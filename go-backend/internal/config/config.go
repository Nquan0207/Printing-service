// Package config reads service settings from the environment.
//
// Every value has a default matching the repo's docker-compose.yml, so
// `go run ./cmd/api` works with no setup. Variable names match the ones the
// crawler already uses.
package config

import (
	"os"
	"strconv"
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
}

func Load() Config {
	return Config{
		Addr:        env("STOCKROOM_ADDR", "127.0.0.1:8080"),
		DatabaseURL: env("STOCKROOM_DATABASE_URL", "postgresql://raksul:raksul_password@127.0.0.1:5432/stockroom"),
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

func boolEnv(key string, fallback bool) bool {
	v, err := strconv.ParseBool(os.Getenv(key))
	if err != nil {
		return fallback
	}
	return v
}
