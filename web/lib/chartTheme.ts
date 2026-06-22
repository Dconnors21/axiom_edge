// One shared chart theme fed into every visx chart so they read as identical
// siblings. Mirrors DESIGN.md tokens. Mono tabular axis labels, muted 1px grid,
// accent for the primary series, no chartjunk.

export const chart = {
  accent: "#E9B24A",
  pos: "#34D399",
  neg: "#F2615C",
  grid: "rgba(255,255,255,0.08)",
  axis: "#6B6F76",
  reference: "#3A3D42", // diagonal / baseline guide
  series: "#A1A4AB",
  fontMono: "var(--font-geist-mono), ui-monospace, monospace",
};

export const tickLabelProps = () =>
  ({
    fill: chart.axis,
    fontFamily: chart.fontMono,
    fontSize: 10,
    fontVariant: "tabular-nums",
  }) as const;

export const axisLabelProps = {
  fill: chart.axis,
  fontFamily: "var(--font-geist-sans), system-ui, sans-serif",
  fontSize: 11,
  letterSpacing: "0.06em",
  textAnchor: "middle" as const,
};
