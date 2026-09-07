package httpapi

import (
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"time"

	"github.com/octguy/stockroom/internal/store"
)

// maxChatContent bounds one stored line. The chat app already caps a user
// prompt at 4000 characters; assistant prose and tool payloads are larger, so
// this is generous rather than tight.
const maxChatContent = 64000

// chatHistoryLimit is how much transcript a resume loads. Older lines stay in
// Postgres but are not replayed -- the model's own context window is smaller
// than this anyway.
const chatHistoryLimit = 200

type chatMessageJSON struct {
	ID        int64           `json:"id"`
	Role      string          `json:"role"`
	Content   string          `json:"content"`
	ToolName  *string         `json:"tool_name"`
	Payload   json.RawMessage `json:"payload"`
	CreatedAt time.Time       `json:"created_at"`
}

type chatMessagesJSON struct {
	Messages []chatMessageJSON `json:"messages"`
	Count    int               `json:"count"`
}

type appendChatMessageRequest struct {
	Role     string          `json:"role"`
	Content  string          `json:"content"`
	ToolName *string         `json:"tool_name"`
	Payload  json.RawMessage `json:"payload"`
}

func toChatMessage(m store.ChatMessage) chatMessageJSON {
	return chatMessageJSON{
		ID:        m.ID,
		Role:      m.Role,
		Content:   m.Content,
		ToolName:  m.ToolName,
		Payload:   json.RawMessage(m.Payload),
		CreatedAt: m.CreatedAt,
	}
}

// ChatMessages returns the caller's rolling transcript, oldest line first.
//
// Scoped to currentUserID like the cart: there is no route that reads another
// user's conversation.
func (s *Server) ChatMessages(w http.ResponseWriter, r *http.Request) {
	limit := chatHistoryLimit
	if raw := r.URL.Query().Get("limit"); raw != "" {
		parsed, err := strconv.Atoi(raw)
		if err != nil || parsed < 1 || parsed > 1000 {
			writeError(w, http.StatusBadRequest, CodeInvalidRequest, "limit must be between 1 and 1000.")
			return
		}
		limit = parsed
	}

	messages, err := s.store.ChatMessages(r.Context(), s.currentUserID(r), limit)
	if err != nil {
		writeInternal(w, "read chat messages", err)
		return
	}
	out := make([]chatMessageJSON, 0, len(messages))
	for _, m := range messages {
		out = append(out, toChatMessage(m))
	}
	writeJSON(w, http.StatusOK, chatMessagesJSON{Messages: out, Count: len(out)})
}

// AppendChatMessage stores one line. The chat app calls this as the
// conversation happens rather than saving a whole transcript at the end, so an
// interrupted stream keeps whatever the user already saw.
func (s *Server) AppendChatMessage(w http.ResponseWriter, r *http.Request) {
	var req appendChatMessageRequest
	if !decodeJSON(w, r, &req) {
		return
	}
	if len(req.Content) > maxChatContent {
		writeError(w, http.StatusBadRequest, CodeInvalidRequest, "content is too long.")
		return
	}
	if len(req.Payload) > maxChatContent {
		writeError(w, http.StatusBadRequest, CodeInvalidRequest, "payload is too long.")
		return
	}
	// json.RawMessage arrives verbatim, so an explicit null must not reach the
	// JSONB column as the string "null".
	payload := req.Payload
	if string(payload) == "null" {
		payload = nil
	}

	message, err := s.store.AppendChatMessage(
		r.Context(), s.currentUserID(r), req.Role, req.Content, req.ToolName, payload)
	if errors.Is(err, store.ErrInvalidRole) {
		writeError(w, http.StatusBadRequest, CodeInvalidRequest, "role must be user, assistant or tool.")
		return
	}
	if err != nil {
		writeInternal(w, "append chat message", err)
		return
	}
	writeJSON(w, http.StatusCreated, toChatMessage(message))
}

// ClearChatMessages empties the caller's transcript, backing "new chat".
func (s *Server) ClearChatMessages(w http.ResponseWriter, r *http.Request) {
	if err := s.store.ClearChatMessages(r.Context(), s.currentUserID(r)); err != nil {
		writeInternal(w, "clear chat messages", err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}
