export const yen = (n: number) => "¥" + Number(n ?? 0).toLocaleString("ja-JP");

/** Compact yen for axis labels, where ¥1,002,770 would collide with its neighbour. */
export function shortYen(n: number): string {
  if (n >= 1_000_000) return "¥" + (n / 1_000_000).toFixed(n >= 10_000_000 ? 0 : 1) + "M";
  if (n >= 1_000) return "¥" + Math.round(n / 1_000) + "k";
  return "¥" + n;
}

/** "2026-09-06" -> "09-06". The year is in the range selector, not on 90 ticks. */
export const shortDate = (iso: string) => iso.slice(5);

export const asDate = (iso: string) => new Date(iso).toLocaleDateString();
