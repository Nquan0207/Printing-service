export const yen = (v: unknown) =>
  Number.isInteger(v) ? `¥${(v as number).toLocaleString()}` : "—";

/** "2026-09-07T14:22:31Z" -> a short local date. */
export const shortDate = (iso: string) =>
  iso ? new Date(iso).toLocaleDateString() : "";

export const STATUS_COLOR: Record<string, string> = {
  confirmed: "teal",
  pending: "yellow",
  cancelled: "red",
};
