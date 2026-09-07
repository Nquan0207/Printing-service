package httpapi

import (
	"regexp"
	"strings"

	"github.com/octguy/stockroom/internal/store"
)

// Category filters arrive as human words, not slugs.
//
// A model asked for "copy paper" says exactly that; a shopper's dropdown sends
// "copy_paper_toner". Resolving here rather than in the caller means a caller
// needs no prior knowledge of the catalog -- and so no extra request to fetch
// the category list before it can filter.

var separators = regexp.MustCompile(`[\s_\-/·・]+`)

// fold strips case and separators so "copy paper" reaches "copy_paper_toner".
func fold(text string) string {
	return separators.ReplaceAllString(strings.ToLower(text), "")
}

// resolveCategories turns requested words into real slugs, returning the
// matches and the tokens that matched nothing.
//
// An exact slug hit wins outright. Only when a token matches no slug does it
// fall back to substring matching over slug and display name -- otherwise a
// short slug would drag in every longer slug that contains it, silently
// widening a filter the caller spelled correctly.
func resolveCategories(tokens []string, categories []store.Category) (matched, unmatched []string) {
	if len(tokens) == 0 {
		return nil, nil
	}

	bySlug := make(map[string]string, len(categories)) // folded slug -> slug
	for _, c := range categories {
		bySlug[fold(c.Slug)] = c.Slug
	}

	seen := map[string]bool{}
	for _, raw := range tokens {
		token := fold(raw)
		if token == "" {
			continue
		}

		if slug, ok := bySlug[token]; ok {
			if !seen[slug] {
				seen[slug] = true
				matched = append(matched, slug)
			}
			continue
		}

		hit := false
		for _, c := range categories {
			if strings.Contains(fold(c.Slug), token) || strings.Contains(fold(c.Name), token) {
				hit = true
				if !seen[c.Slug] {
					seen[c.Slug] = true
					matched = append(matched, c.Slug)
				}
			}
		}
		if !hit {
			unmatched = append(unmatched, raw)
		}
	}
	return matched, unmatched
}
