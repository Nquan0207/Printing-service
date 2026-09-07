package store

import (
	"context"
	"errors"
	"fmt"
	"time"
)

// ErrInvalidRole rejects a role the schema's CHECK constraint would refuse,
// so the caller gets a 400 rather than a 500 from Postgres.
var ErrInvalidRole = errors.New("invalid chat role")

// chatRoles mirrors the CHECK constraint on chat_messages.role.
var chatRoles = map[string]bool{"user": true, "assistant": true, "tool": true}

// ChatMessage is one line of a user's rolling chat transcript. Payload holds
// the structured MCP tool result for role "tool" and is nil otherwise; it is
// raw JSON so the store never has to know a tool's result shape.
type ChatMessage struct {
	ID        int64
	Role      string
	Content   string
	ToolName  *string
	Payload   []byte
	CreatedAt time.Time
}

// ChatMessages returns the newest `limit` messages for one user in the order
// they were written. The window is taken from the end and then reversed, so a
// long-running conversation costs the same to load as a short one.
func (s *Store) ChatMessages(ctx context.Context, userID int64, limit int) ([]ChatMessage, error) {
	if limit <= 0 {
		limit = 200
	}
	rows, err := s.pool.Query(ctx, `
		SELECT id, role, content, tool_name, payload, created_at
		FROM (
			SELECT id, role, content, tool_name, payload, created_at
			FROM chat_messages
			WHERE user_id = $1
			ORDER BY id DESC
			LIMIT $2
		) recent
		ORDER BY id`, userID, limit)
	if err != nil {
		return nil, fmt.Errorf("query chat messages: %w", err)
	}
	defer rows.Close()

	out := []ChatMessage{}
	for rows.Next() {
		var m ChatMessage
		if err := rows.Scan(&m.ID, &m.Role, &m.Content, &m.ToolName, &m.Payload, &m.CreatedAt); err != nil {
			return nil, fmt.Errorf("scan chat message: %w", err)
		}
		out = append(out, m)
	}
	return out, rows.Err()
}

// AppendChatMessage adds one line to a user's transcript. payload must be
// valid JSON or nil -- Postgres validates it on the way in.
func (s *Store) AppendChatMessage(
	ctx context.Context, userID int64, role, content string, toolName *string, payload []byte,
) (ChatMessage, error) {
	if !chatRoles[role] {
		return ChatMessage{}, ErrInvalidRole
	}
	// A nil []byte would be sent as JSON null rather than SQL NULL.
	var raw any
	if len(payload) > 0 {
		raw = payload
	}

	var m ChatMessage
	err := s.pool.QueryRow(ctx, `
		INSERT INTO chat_messages (user_id, role, content, tool_name, payload)
		VALUES ($1, $2, $3, $4, $5)
		RETURNING id, role, content, tool_name, payload, created_at`,
		userID, role, content, toolName, raw,
	).Scan(&m.ID, &m.Role, &m.Content, &m.ToolName, &m.Payload, &m.CreatedAt)
	if err != nil {
		return ChatMessage{}, fmt.Errorf("insert chat message: %w", err)
	}
	return m, nil
}

// ClearChatMessages drops a user's whole transcript. Used by "new chat" and by
// sign-out; deleting the user cascades here anyway.
func (s *Store) ClearChatMessages(ctx context.Context, userID int64) error {
	if _, err := s.pool.Exec(ctx, `DELETE FROM chat_messages WHERE user_id = $1`, userID); err != nil {
		return fmt.Errorf("delete chat messages: %w", err)
	}
	return nil
}
