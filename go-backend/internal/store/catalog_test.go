package store

import (
	"context"
	"errors"
	"os"
	"strings"
	"testing"
)

// Integration tests run against a real Postgres holding crawled data. They
// assert invariants that hold for any catalog rather than hard-coding ids, so
// a re-crawl never breaks them.
//
//	STOCKROOM_TEST_DATABASE_URL=postgresql://raksul:raksul_password@127.0.0.1:5432/stockroom go test ./...
func testStore(t *testing.T) *Store {
	t.Helper()
	url := os.Getenv("STOCKROOM_TEST_DATABASE_URL")
	if url == "" {
		t.Skip("set STOCKROOM_TEST_DATABASE_URL to run Postgres integration tests")
	}
	s, err := New(context.Background(), url)
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	t.Cleanup(s.Close)
	return s
}

func TestCategoriesAllHoldProducts(t *testing.T) {
	s := testStore(t)
	ctx := context.Background()

	categories, err := s.Categories(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if len(categories) == 0 {
		t.Skip("catalog is empty; run the crawler first")
	}
	for _, c := range categories {
		got, err := s.SearchProducts(ctx, ProductFilter{CategorySlug: c.Slug})
		if err != nil {
			t.Fatal(err)
		}
		if len(got) == 0 {
			t.Errorf("category %q is listed but holds no products", c.Slug)
		}
	}
}

// Sizes must ascend by price so they render S, M, L. Ordering by size_name
// would give L, M, S.
func TestSizesAscendByPrice(t *testing.T) {
	s := testStore(t)
	products, err := s.SearchProducts(context.Background(), ProductFilter{})
	if err != nil {
		t.Fatal(err)
	}
	if len(products) == 0 {
		t.Skip("catalog is empty; run the crawler first")
	}
	for _, p := range products {
		for i := 1; i < len(p.Sizes); i++ {
			if p.Sizes[i].PriceAdjustmentJPY < p.Sizes[i-1].PriceAdjustmentJPY {
				t.Fatalf("product %d sizes out of order: %v", p.ID, p.Sizes)
			}
		}
	}
}

// The contract's rule: a product matches when *one* size falls inside both
// bounds. Two separate EXISTS clauses would wrongly admit a product whose S is
// under max and whose L is over min.
func TestPriceFilterMatchesASingleSize(t *testing.T) {
	s := testStore(t)
	ctx := context.Background()

	all, err := s.SearchProducts(ctx, ProductFilter{})
	if err != nil {
		t.Fatal(err)
	}
	if len(all) == 0 {
		t.Skip("catalog is empty; run the crawler first")
	}

	// Find a product with a gap between two consecutive sizes, then query the
	// gap: it must be excluded even though it has sizes on either side.
	for _, p := range all {
		if len(p.Sizes) < 2 {
			continue
		}
		low := p.BasePriceJPY + p.Sizes[0].PriceAdjustmentJPY
		high := p.BasePriceJPY + p.Sizes[1].PriceAdjustmentJPY
		if high-low < 3 {
			continue // no room for a gap strictly between them
		}
		min, max := low+1, high-1

		got, err := s.SearchProducts(ctx, ProductFilter{MinPriceJPY: &min, MaxPriceJPY: &max})
		if err != nil {
			t.Fatal(err)
		}
		for _, candidate := range got {
			if candidate.ID != p.ID {
				continue
			}
			t.Fatalf("product %d matched [%d,%d] but no single size is in range: %v",
				p.ID, min, max, p.Sizes)
		}

		// Every product that *did* match must have a size inside the bounds.
		for _, candidate := range got {
			inRange := false
			for _, sz := range candidate.Sizes {
				unit := candidate.BasePriceJPY + sz.PriceAdjustmentJPY
				if unit >= min && unit <= max {
					inRange = true
					break
				}
			}
			if !inRange {
				t.Errorf("product %d matched [%d,%d] with no size in range", candidate.ID, min, max)
			}
		}
		return
	}
	t.Skip("no product has a usable price gap between sizes")
}

func TestProductRoundTripsAndReportsMissing(t *testing.T) {
	s := testStore(t)
	ctx := context.Background()

	products, err := s.SearchProducts(ctx, ProductFilter{})
	if err != nil {
		t.Fatal(err)
	}
	if len(products) == 0 {
		t.Skip("catalog is empty; run the crawler first")
	}

	want := products[0]
	got, err := s.Product(ctx, want.ID)
	if err != nil {
		t.Fatal(err)
	}
	if got.Name != want.Name || got.Category.Slug != want.Category.Slug {
		t.Errorf("Product(%d) = %q/%s, want %q/%s",
			want.ID, got.Name, got.Category.Slug, want.Name, want.Category.Slug)
	}
	if len(got.Sizes) != len(want.Sizes) {
		t.Errorf("Product(%d) has %d sizes, search returned %d", want.ID, len(got.Sizes), len(want.Sizes))
	}

	if _, err := s.Product(ctx, 1<<40); !errors.Is(err, ErrNotFound) {
		t.Errorf("missing product err = %v, want ErrNotFound", err)
	}
}

func TestTextSearchMatchesNameOrDescription(t *testing.T) {
	s := testStore(t)
	ctx := context.Background()

	products, err := s.SearchProducts(ctx, ProductFilter{Query: "紙"})
	if err != nil {
		t.Fatal(err)
	}
	for _, p := range products {
		name := p.Name
		description := ""
		if p.Description != nil {
			description = *p.Description
		}
		if !strings.Contains(name, "紙") && !strings.Contains(description, "紙") {
			t.Errorf("product %d matched %q in neither name nor description", p.ID, "紙")
		}
	}
}
