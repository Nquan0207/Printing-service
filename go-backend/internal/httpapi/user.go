package httpapi

import (
	"errors"
	"net/http"
	"strconv"

	"github.com/octguy/stockroom/internal/store"
)

// UserHeader carries the id the MCP server resolved into its UserContext.
//
// It is trusted WITHOUT verification. That is safe only because this service
// binds 127.0.0.1 and the MCP server is its sole client; exposed, the header
// would be a free impersonation switch. See
// docs/api-contract.md#the-trust-boundary.
const UserHeader = "X-Stockroom-User"

type loginRequest struct {
	Email string `json:"email"`
	Name  string `json:"name"`
}

type loginResponse struct {
	UserID  int64  `json:"user_id"`
	Email   string `json:"email"`
	Name    string `json:"name"`
	Created bool   `json:"created"`
}

// Login resolves an email to a user id, creating the user when the address is
// new. This is NOT authentication: no password is taken and nothing is
// verified. It exists so the custom chat can pick or add a demo user.
func (s *Server) Login(w http.ResponseWriter, r *http.Request) {
	var req loginRequest
	if !decodeJSON(w, r, &req) {
		return
	}

	user, err := s.store.UpsertUser(r.Context(), req.Email, req.Name)
	if errors.Is(err, store.ErrInvalidEmail) {
		writeError(w, http.StatusBadRequest, CodeInvalidRequest, "A valid email is required.")
		return
	}
	if err != nil {
		writeInternal(w, "login", err)
		return
	}
	writeJSON(w, http.StatusOK, loginResponse{
		UserID:  user.ID,
		Email:   user.Email,
		Name:    user.Name,
		Created: user.Created,
	})
}

// currentUserID is the single seam between transport and business logic.
// Swapping the PoC's trusted header for a verified token later changes this
// one function -- every query already filters on the id it returns.
func (s *Server) currentUserID(r *http.Request) int64 {
	if id, err := strconv.ParseInt(r.Header.Get(UserHeader), 10, 64); err == nil && id > 0 {
		return id
	}
	return s.defaultUserID
}
