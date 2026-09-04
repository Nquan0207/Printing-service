package httpapi

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/octguy/stockroom/internal/store"
)

func product(id int64, categoryID int64, categoryName string, base int, adjustments ...int) store.Product {
	p := store.Product{
		ID:           id,
		Name:         "product",
		BasePriceJPY: base,
		Category:     store.Category{ID: categoryID, Slug: "slug", Name: categoryName},
	}
	for i, adj := range adjustments {
		p.Sizes = append(p.Sizes, store.Size{ID: id*100 + int64(i), Name: "S", PriceAdjustmentJPY: adj})
	}
	return p
}

func TestGroupByCategoryOrdersByCountThenName(t *testing.T) {
	products := []store.Product{
		product(1, 1, "Bravo", 100),
		product(2, 2, "Alpha", 100),
		product(3, 2, "Alpha", 100),
		product(4, 3, "Charlie", 100),
	}
	got := groupByCategory(products, defaultLimit, 0)

	var names []string
	for _, g := range got.Groups {
		names = append(names, g.Category.Name)
	}
	// Alpha has 2 products so it leads; Bravo and Charlie tie at 1 and fall
	// back to name order.
	want := []string{"Alpha", "Bravo", "Charlie"}
	if strings.Join(names, ",") != strings.Join(want, ",") {
		t.Errorf("group order = %v, want %v", names, want)
	}
	if got.Count != 4 {
		t.Errorf("count = %d, want 4", got.Count)
	}
}

func TestGroupByCategoryPerCategoryCapsEachGroup(t *testing.T) {
	products := []store.Product{
		product(1, 1, "Alpha", 100), product(2, 1, "Alpha", 100), product(3, 1, "Alpha", 100),
		product(4, 2, "Bravo", 100), product(5, 2, "Bravo", 100),
	}
	got := groupByCategory(products, defaultLimit, 2)

	for _, g := range got.Groups {
		if len(g.Products) > 2 {
			t.Errorf("group %s has %d products, want <= 2", g.Category.Name, len(g.Products))
		}
		if g.Count != len(g.Products) {
			t.Errorf("group %s count = %d, want %d", g.Category.Name, g.Count, len(g.Products))
		}
	}
	if got.Count != 4 { // 2 from each group
		t.Errorf("count = %d, want 4", got.Count)
	}
}

func TestGroupByCategoryLimitCapsTotalAcrossGroups(t *testing.T) {
	products := []store.Product{
		product(1, 1, "Alpha", 100), product(2, 1, "Alpha", 100), product(3, 1, "Alpha", 100),
		product(4, 2, "Bravo", 100), product(5, 2, "Bravo", 100),
	}
	got := groupByCategory(products, 4, 0)

	total := 0
	for _, g := range got.Groups {
		total += len(g.Products)
		if g.Count != len(g.Products) {
			t.Errorf("group %s count = %d, want %d", g.Category.Name, g.Count, len(g.Products))
		}
	}
	if total != 4 || got.Count != 4 {
		t.Errorf("total = %d, count = %d, want 4 and 4", total, got.Count)
	}
}

// A section header with nothing under it is a UI bug, so an exhausted budget
// must drop whole groups rather than emit empty ones.
func TestGroupByCategoryNeverEmitsAnEmptyGroup(t *testing.T) {
	products := []store.Product{
		product(1, 1, "Alpha", 100), product(2, 1, "Alpha", 100),
		product(3, 2, "Bravo", 100),
	}
	got := groupByCategory(products, 2, 0)

	for _, g := range got.Groups {
		if len(g.Products) == 0 {
			t.Errorf("group %s is empty", g.Category.Name)
		}
	}
}

// Views iterate response.groups directly; JSON null would crash that loop.
func TestEmptyResultMarshalsAsEmptyArrayNotNull(t *testing.T) {
	body, err := json.Marshal(groupByCategory(nil, defaultLimit, 0))
	if err != nil {
		t.Fatal(err)
	}
	if got := string(body); got != `{"groups":[],"count":0}` {
		t.Errorf("empty result = %s, want {\"groups\":[],\"count\":0}", got)
	}
}

func TestToProductComputesUnitPriceAndMediaPaths(t *testing.T) {
	p := product(1, 1, "Alpha", 168, 0, 18, 30)
	p.ImageKeys = []string{"products/158/abc.jpg"}

	got := toProduct(p, false)

	want := []int{168, 186, 198}
	for i, size := range got.Sizes {
		if size.UnitPriceJPY != want[i] {
			t.Errorf("size %d unit price = %d, want %d", i, size.UnitPriceJPY, want[i])
		}
	}
	if got.Images[0] != "/media/products/158/abc.jpg" {
		t.Errorf("image = %q, want a same-origin /media path", got.Images[0])
	}
}

func TestDescriptionOnlyOnDetail(t *testing.T) {
	description := "long text"
	p := product(1, 1, "Alpha", 100, 0)
	p.Description = &description

	if got := toProduct(p, false); got.Description != nil {
		t.Error("search results must omit description")
	}
	if got := toProduct(p, true); got.Description == nil {
		t.Error("detail must include description")
	}
}

func TestProductWithoutImagesMarshalsAsEmptyArray(t *testing.T) {
	body, err := json.Marshal(toProduct(product(1, 1, "Alpha", 100, 0), false))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(body), `"images":[]`) {
		t.Errorf("missing images should marshal as [], got %s", body)
	}
}

func TestIntParamBounds(t *testing.T) {
	tests := []struct {
		raw     string
		want    int
		wantErr bool
	}{
		{"", defaultLimit, false},
		{"5", 5, false},
		{"100", 100, false},
		{"0", 0, true},
		{"101", 0, true},
		{"abc", 0, true},
		{"-1", 0, true},
	}
	for _, tt := range tests {
		got, err := intParam(tt.raw, defaultLimit, 1, maxLimit)
		if (err != nil) != tt.wantErr {
			t.Errorf("intParam(%q) err = %v, wantErr %v", tt.raw, err, tt.wantErr)
			continue
		}
		if err == nil && got != tt.want {
			t.Errorf("intParam(%q) = %d, want %d", tt.raw, got, tt.want)
		}
	}
}

func TestOptionalIntRejectsNegative(t *testing.T) {
	if got, err := optionalInt(""); err != nil || got != nil {
		t.Errorf(`optionalInt("") = %v, %v; want nil, nil`, got, err)
	}
	if got, err := optionalInt("0"); err != nil || got == nil || *got != 0 {
		t.Errorf(`optionalInt("0") = %v, %v; want 0, nil`, got, err)
	}
	if _, err := optionalInt("-5"); err == nil {
		t.Error("negative price bound should be rejected")
	}
}
