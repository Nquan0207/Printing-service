package store

import (
	"context"
	"errors"
	"testing"
)

func TestPricedSizeResolvesUnitPrice(t *testing.T) {
	s := testStore(t)
	ctx := context.Background()

	products, err := s.SearchProducts(ctx, ProductFilter{})
	if err != nil {
		t.Fatal(err)
	}
	if len(products) == 0 {
		t.Skip("catalog is empty; run the crawler first")
	}

	p := products[0]
	for _, size := range p.Sizes {
		got, err := s.PricedSize(ctx, p.ID, size.ID)
		if err != nil {
			t.Fatalf("PricedSize(%d, %d) = %v", p.ID, size.ID, err)
		}
		want := p.BasePriceJPY + size.PriceAdjustmentJPY
		if got.UnitPriceJPY != want {
			t.Errorf("size %s unit price = %d, want %d", size.Name, got.UnitPriceJPY, want)
		}
		if got.ProductName != p.Name || got.SizeName != size.Name {
			t.Errorf("PricedSize returned %q/%q, want %q/%q",
				got.ProductName, got.SizeName, p.Name, size.Name)
		}
	}
}

// A size id that exists but belongs to another product must not silently
// price against the product the caller named.
func TestPricedSizeRejectsSizeFromAnotherProduct(t *testing.T) {
	s := testStore(t)
	ctx := context.Background()

	products, err := s.SearchProducts(ctx, ProductFilter{})
	if err != nil {
		t.Fatal(err)
	}
	if len(products) < 2 {
		t.Skip("need at least two products")
	}

	first, second := products[0], products[1]
	if len(second.Sizes) == 0 {
		t.Skip("second product has no sizes")
	}

	_, err = s.PricedSize(ctx, first.ID, second.Sizes[0].ID)
	if !errors.Is(err, ErrSizeNotFound) {
		t.Errorf("PricedSize(product %d, size of product %d) = %v, want ErrSizeNotFound",
			first.ID, second.ID, err)
	}
}

func TestPricedSizeDistinguishesMissingProductFromMissingSize(t *testing.T) {
	s := testStore(t)
	ctx := context.Background()

	products, err := s.SearchProducts(ctx, ProductFilter{})
	if err != nil {
		t.Fatal(err)
	}
	if len(products) == 0 {
		t.Skip("catalog is empty; run the crawler first")
	}

	if _, err := s.PricedSize(ctx, 1<<40, 1); !errors.Is(err, ErrNotFound) {
		t.Errorf("missing product = %v, want ErrNotFound", err)
	}
	if _, err := s.PricedSize(ctx, products[0].ID, 1<<40); !errors.Is(err, ErrSizeNotFound) {
		t.Errorf("missing size = %v, want ErrSizeNotFound", err)
	}
}
