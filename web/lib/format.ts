// Display formatting. Numbers render inside elements carrying the `.tnum` class
// (mono + tabular-nums) per the DESIGN.md numerics rule.

export const pct = (x: number, dp = 1) => `${(x * 100).toFixed(dp)}%`;

export const signedPct = (x: number, dp = 1) =>
  `${x >= 0 ? "+" : ""}${(x * 100).toFixed(dp)}%`;

export const odds = (n: number | null | undefined) =>
  n == null ? "—" : n > 0 ? `+${n}` : `${n}`;

export const signed = (x: number, dp = 2) =>
  `${x >= 0 ? "+" : ""}${x.toFixed(dp)}`;

export const americanToDecimal = (n: number) =>
  n > 0 ? n / 100 + 1 : 100 / Math.abs(n) + 1;

export const decimalToAmerican = (d: number) =>
  d >= 2 ? Math.round((d - 1) * 100) : Math.round(-100 / (d - 1));

export function tipET(commence: string): string {
  if (!commence) return "";
  const d = new Date(commence);
  if (isNaN(d.getTime())) return "";
  return d
    .toLocaleTimeString("en-US", {
      hour: "numeric",
      minute: "2-digit",
      timeZone: "America/New_York",
    })
    .replace(/^0/, "") + " ET";
}

export function slateDateLong(iso: string | null): string {
  if (!iso) return "No slate";
  const d = new Date(`${iso}T12:00:00`);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
  });
}
