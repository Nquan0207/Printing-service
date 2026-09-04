package httpapi

import "testing"

// Money lands in INTEGER columns, so a subtotal past int32 must be refused at
// the quote rather than blowing up on INSERT at checkout.
func TestSubtotalRejectsOverflow(t *testing.T) {
	tests := []struct {
		unitPrice, quantity int
		want                int
		ok                  bool
	}{
		{168, 500, 84000, true},
		{1, maxMoneyJPY, maxMoneyJPY, true},
		{2, maxMoneyJPY, 0, false},
		{12461, 200000, 0, false},
		{168, 0, 0, false},
		{168, -1, 0, false},
	}
	for _, tt := range tests {
		got, ok := subtotalJPY(tt.unitPrice, tt.quantity)
		if ok != tt.ok {
			t.Errorf("subtotalJPY(%d, %d) ok = %v, want %v", tt.unitPrice, tt.quantity, ok, tt.ok)
			continue
		}
		if ok && got != tt.want {
			t.Errorf("subtotalJPY(%d, %d) = %d, want %d", tt.unitPrice, tt.quantity, got, tt.want)
		}
	}
}

func TestSubtotalHandlesFreeItems(t *testing.T) {
	got, ok := subtotalJPY(0, 1000)
	if !ok || got != 0 {
		t.Errorf("subtotalJPY(0, 1000) = %d, %v; want 0, true", got, ok)
	}
}
