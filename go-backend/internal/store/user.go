package store

import (
	"context"
	"errors"
	"fmt"
	"strings"
)

// DefaultUserEmail is seeded at startup so requests arriving without an
// X-Stockroom-User header always resolve to somebody -- external hosts like
// Claude and ChatGPT never call login.
const DefaultUserEmail = "alice@stockroom.local"

// unusablePasswordHash is a sentinel, not a hash. No login path checks a
// credential, so nothing can ever authenticate as these accounts.
const unusablePasswordHash = "!unusable-poc-account!"

var ErrInvalidEmail = errors.New("invalid email")

type User struct {
	ID      int64
	Email   string
	Name    string
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
		RETURNING id, email, name, (xmax = 0) AS created`,
		strings.TrimSpace(name), normalized, unusablePasswordHash,
	).Scan(&out.ID, &out.Email, &out.Name, &out.Created)
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
