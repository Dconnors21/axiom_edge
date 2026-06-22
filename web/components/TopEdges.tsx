import type { Slate, Side } from "@/types/api";
import { pct, signedPct, odds, tipET } from "@/lib/format";

const LEAGUE_LABEL: Record<string, string> = { nba: "NBA", mlb: "MLB", nhl: "NHL" };

type Edge = {
  league: string;
  matchup: string;
  team: string;
  prob: number;
  edge: number;
  ev: number;
  kelly: number;
  price: number | null;
  flag: string;
  tip: string;
  conviction: number;
};

const conviction = (s: Side) =>
  0.4 * s.edge + 0.35 * Math.max(0, s.model_prob - 0.5) + 0.25 * s.kelly;

function collect(slates: Slate[]): Edge[] {
  const edges: Edge[] = [];
  for (const slate of slates) {
    for (const g of slate.games) {
      for (const side of [g.home, g.away]) {
        if (!side.is_value) continue;
        edges.push({
          league: slate.league,
          matchup: `${g.away_team} @ ${g.home_team}`,
          team: side.team,
          prob: side.model_prob,
          edge: side.edge,
          ev: side.ev_per_unit,
          kelly: side.kelly,
          price: side.price,
          flag: g.market_flag,
          tip: tipET(g.commence_time),
          conviction: conviction(side),
        });
      }
    }
  }
  return edges.sort((a, b) => b.conviction - a.conviction);
}

export default function TopEdges({ slates, limit = 6 }: { slates: Slate[]; limit?: number }) {
  const edges = collect(slates).slice(0, limit);

  return (
    <section>
      <div className="flex items-baseline justify-between pb-3">
        <h3 className="text-[11px] font-bold uppercase tracking-[0.12em] text-text-secondary">
          Top edges today
        </h3>
        <span className="text-[11px] text-text-tertiary">across all leagues</span>
      </div>

      {edges.length === 0 ? (
        <p className="rounded-md border border-border-subtle bg-surface px-5 py-6 text-sm text-text-secondary">
          No value bets on the board. Every line is within model tolerance.
        </p>
      ) : (
        <div className="overflow-hidden rounded-md border border-border-subtle">
          {/* header */}
          <div className="grid grid-cols-[auto_1fr_auto_auto_auto] items-center gap-4 border-b border-border-subtle bg-surface px-5 py-2.5 text-[10px] font-semibold uppercase tracking-[0.06em] text-text-tertiary">
            <span className="w-8">Lg</span>
            <span>Pick</span>
            <span className="w-16 text-right">Model</span>
            <span className="w-16 text-right">Edge</span>
            <span className="w-14 text-right">Line</span>
          </div>
          {edges.map((e, i) => (
            <div
              key={`${e.league}-${e.team}-${i}`}
              className={`grid grid-cols-[auto_1fr_auto_auto_auto] items-center gap-4 bg-surface px-5 py-3 transition-colors duration-[var(--dur-micro)] hover:bg-surface-elevated ${
                i > 0 ? "border-t border-border-subtle" : ""
              }`}
            >
              <span className="tnum w-8 text-[11px] font-medium text-text-tertiary">
                {LEAGUE_LABEL[e.league]}
              </span>
              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-text-primary">{e.team}</div>
                <div className="truncate text-[11px] text-text-tertiary">
                  {e.matchup} · {e.tip}
                  {e.flag ? ` · ${e.flag}` : ""}
                </div>
              </div>
              <span className="tnum w-16 text-right text-sm text-text-primary">{pct(e.prob)}</span>
              <span className="tnum w-16 text-right text-sm font-semibold text-pos">
                {signedPct(e.edge)}
              </span>
              <span className="tnum w-14 text-right text-sm text-text-secondary">
                {odds(e.price)}
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
