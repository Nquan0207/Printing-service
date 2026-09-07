/**
 * Chart palette — validated, not chosen by eye.
 *
 * Checked with the dataviz validator against both surfaces:
 *
 *   #ef1f1f,#087f5b,#d9480f,#3b5bdb  --mode light  -> ALL CHECKS PASS
 *   #ef1f1f,#087f5b,#d9480f,#3b5bdb  --mode dark   -> ALL CHECKS PASS
 *
 * What it replaced and why:
 *   teal-6   #12b886  contrast 2.49:1 vs the light surface (WARN)
 *   yellow-6 #fab005  L 0.807 — outside the 0.43–0.77 light band (FAIL),
 *                     contrast 1.81:1; those bars were barely visible
 *   indigo-5 #5c7cfa  re-stepped for the same reason
 *
 * The light band is L 0.43–0.77 and the dark band 0.48–0.67, so a palette that
 * passes light can still fail dark — these steps sit inside both, which is why
 * one set serves each mode rather than flipping.
 *
 * Re-run before changing any value:
 *   node scripts/validate_palette.js "<hex,…>" --mode light   (and --mode dark)
 */

/** Revenue over time. The brand red, which already sits in both bands. */
export const SERIES_REVENUE = "#ef1f1f";
/** Order counts. */
export const SERIES_ORDERS = "#087f5b";
/** Unit price distribution. */
export const SERIES_PRICE = "#d9480f";
/** Products per category. */
export const SERIES_CATEGORY = "#3b5bdb";
