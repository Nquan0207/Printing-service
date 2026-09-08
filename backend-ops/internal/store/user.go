package store

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"github.com/jackc/pgx/v5"
)

// DefaultUserEmail is seeded at startup so requests arriving without an
// X-Stockroom-User header always resolve to somebody -- external hosts like
// Claude and ChatGPT never call login.
const DefaultUserEmail = "alice@stockroom.local"

// unusablePasswordHash is a sentinel, not a hash. No login path checks a
// credential, so nothing can ever authenticate as these accounts.
const unusablePasswordHash = "!unusable-poc-account!"

var ErrInvalidEmail = errors.New("invalid email")
var ErrAdminIdentityMismatch = errors.New("admin identity mismatch")

const (
	OpsAdminName  = "admin"
	OpsAdminEmail = "admin@gmail.com"
)

type User struct {
	ID      int64
	Email   string
	Name    string
	IsAdmin bool
	Created bool
}

// NormalizeEmail lower-cases and trims so the same address always maps to the
// same row regardless of how it was typed.
func NormalizeEmail(email string) (string, error) {
	normalized := strings.ToLower(strings.TrimSpace(email))
	at := strings.Index(normalized, "@")
	if at <= 0 || at == len(normalized)-1 || strings.Count(normalized, "@") != 1 {
		return "", ErrInvalidEmail
	}
	if strings.ContainsAny(normalized, " \t\r\n") {
		return "", ErrInvalidEmail
	}
	return normalized, nil
}

// NameFromEmail supplies a display name when the caller omits one.
func NameFromEmail(email string) string {
	if at := strings.Index(email, "@"); at > 0 {
		return email[:at]
	}
	return email
}

// UpsertUser resolves an email to a user, creating it when new.
//
// `name` applies only on creation: a returning user's name is never
// overwritten, so calling login on every user switch is safe.
func (s *Store) UpsertUser(ctx context.Context, email, name string) (User, error) {
	normalized, err := NormalizeEmail(email)
	if err != nil {
		return User{}, err
	}
	if strings.TrimSpace(name) == "" {
		name = NameFromEmail(normalized)
	}

	var out User
	// xmax is 0 on a fresh insert and non-zero when ON CONFLICT took the
	// UPDATE branch -- that is how we report `created` without a second query.
	err = s.pool.QueryRow(ctx, `
		INSERT INTO users (name, email, password_hash)
		VALUES ($1, $2, $3)
		ON CONFLICT (email) DO UPDATE SET updated_at = NOW()
		RETURNING id, email, name, is_admin, (xmax = 0) AS created`,
		strings.TrimSpace(name), normalized, unusablePasswordHash,
	).Scan(&out.ID, &out.Email, &out.Name, &out.IsAdmin, &out.Created)
	if err != nil {
		return User{}, fmt.Errorf("upsert user: %w", err)
	}
	return out, nil
}

// EnsureDefaultUser seeds Alice and returns her id, for requests that carry no
// identity header.
func (s *Store) EnsureDefaultUser(ctx context.Context) (int64, error) {
	user, err := s.UpsertUser(ctx, DefaultUserEmail, "Alice")
	if err != nil {
		return 0, err
	}
	return user.ID, nil
}

// IsAdmin reports whether the user may reach /api/v1/admin/*.
//
// Read per request rather than cached, so revoking admin takes effect
// immediately instead of at the next restart.
func (s *Store) IsAdmin(ctx context.Context, userID int64) (bool, error) {
	var isAdmin bool
	err := s.pool.QueryRow(ctx,
		`SELECT is_admin FROM users WHERE id = $1`, userID).Scan(&isAdmin)
	if errors.Is(err, pgx.ErrNoRows) {
		return false, nil // unknown user is simply not an admin
	}
	if err != nil {
		return false, fmt.Errorf("check admin: %w", err)
	}
	return isAdmin, nil
}

// VerifyOpsAdmin reads the fixed ops identity from the database on every call.
// Both submitted values and the stored row must match exactly, and the row
// must still hold admin privilege.
func (s *Store) VerifyOpsAdmin(ctx context.Context, name, email string) (User, error) {
	var user User
	err := s.pool.QueryRow(ctx, `
		SELECT id, email, name, is_admin, FALSE
		FROM users
		WHERE name = $1 AND email = $2
		  AND name = $3 AND email = $4
		  AND is_admin = TRUE`,
		name, email, OpsAdminName, OpsAdminEmail,
	).Scan(&user.ID, &user.Email, &user.Name, &user.IsAdmin, &user.Created)
	if errors.Is(err, pgx.ErrNoRows) {
		return User{}, ErrAdminIdentityMismatch
	}
	if err != nil {
		return User{}, fmt.Errorf("verify ops admin: %w", err)
	}
	return user, nil
}

// GrantAdmin creates the user if needed and marks them admin. Called only at
// startup from configuration -- no HTTP route can grant admin.
func (s *Store) GrantAdmin(ctx context.Context, email string) (User, error) {
	user, err := s.UpsertUser(ctx, email, "")
	if err != nil {
		return User{}, err
	}
	if _, err := s.pool.Exec(ctx,
		`UPDATE users SET is_admin = TRUE, updated_at = NOW() WHERE id = $1`, user.ID); err != nil {
		return User{}, fmt.Errorf("grant admin: %w", err)
	}
	user.IsAdmin = true
	return user, nil
}
