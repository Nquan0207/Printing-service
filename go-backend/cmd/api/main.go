// Command api serves the stockroom catalog, cart, and order API consumed by
// the MCP server. See docs/api-contract.yaml.
package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/octguy/stockroom/internal/config"
	"github.com/octguy/stockroom/internal/httpapi"
	"github.com/octguy/stockroom/internal/media"
	"github.com/octguy/stockroom/internal/store"
)

func main() {
	if err := run(); err != nil {
		slog.Error("fatal", "err", err)
		os.Exit(1)
	}
}

func run() error {
	cfg := config.Load()
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	db, err := store.New(ctx, cfg.DatabaseURL)
	if err != nil {
		return err
	}
	defer db.Close()

	objects, err := media.New(cfg.MinIO)
	if err != nil {
		return err
	}

	// Seed the fallback user before serving, so a request without an identity
	// header can never hit a missing foreign key.
	defaultUserID, err := db.EnsureDefaultUser(ctx)
	if err != nil {
		return err
	}
	slog.Info("default user ready", "id", defaultUserID, "email", store.DefaultUserEmail)

	srv := &http.Server{
		Addr:              cfg.Addr,
		Handler:           httpapi.New(db, objects, defaultUserID).Routes(),
		ReadHeaderTimeout: 5 * time.Second,
	}

	go func() {
		slog.Info("listening", "addr", cfg.Addr)
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			slog.Error("serve", "err", err)
			stop()
		}
	}()

	<-ctx.Done()
	slog.Info("shutting down")
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	return srv.Shutdown(shutdownCtx)
}
