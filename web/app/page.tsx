import type { League, Slate, Performance, Ladder, Insight } from "@/types/api";
import { getSlate, getInsight, getPerformance, getLadder } from "@/lib/api";
import { slateDateLong, pct, signedPct } from "@/lib/format";
import AxiomRead from "@/components/AxiomRead";
import LadderChallenge from "@/components/LadderChallenge";
import TopEdges from "@/components/TopEdges";

const INSIGHT_FALLBACK: Insight = { available: false, market: "moneyline", line_movement: "" };

const LADDER_FALLBACK: Ladder = {
  available: false, reason: "Ladder unavailable right now.", slate_date: null,
  legs: [], combined_american: null, combined_decimal: null, combined_model_prob: null,
  break_even_prob: null, ev_per_unit: null, edge: null, stake: 50, payout: null,
  target_days: 10, projection: [], survival_7: null, survival_10: null,
};

export const dynamic = "force-dynamic"; // live odds — never statically cached

const LEAGUES: League[] = ["mlb", "nba", "nhl"];
const LEAGUE_LABEL: Record<League, string> = { nba: "NBA", mlb: "MLB", nhl: "NHL" };

async function settledSlates(): Promise<Slate[]> {
  const results = await Promise.allSettled(LEAGUES.map(getSlate));
  return results
    .filter((r): r is PromiseFulfilledResult<Slate> => r.status === "fulfilled")
    .map((r) => r.value);
}

function LeagueSummary({ slate }: { slate: Slate }) {
  return (
    <div className="flex flex-col gap-3 bg-surface px-5 py-4">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-text-primary">
          {LEAGUE_LABEL[slate.league]}
        </span>
        <span className="text-[11px] text-text-tertiary">
          {slate.game_count === 0 ? "no slate" : `${slate.game_count} games`}
        </span>
      </div>
      <div className="flex items-end justify-between">
        <div className="flex flex-col gap-0.5">
          <span className="text-[10px] uppercase tracking-[0.06em] text-text-secondary">
            Value bets
          </span>
          <span className="tnum text-lg font-semibold text-text-primary">
            {slate.value_count}
          </span>
        </div>
        <div className="flex flex-col items-end gap-0.5">
          <span className="text-[10px] uppercase tracking-[0.06em] text-text-secondary">
            Best edge
          </span>
          <span className="tnum text-lg font-semibold text-pos">
            {slate.best_edge > 0 ? signedPct(slate.best_edge) : "—"}
          </span>
        </div>
      </div>
    </div>
  );
}

function PerfGlance({ perf }: { perf: Performance }) {
  const record = perf.record_n > 0 ? `${perf.wins}–${perf.losses}` : "—";
  return (
    <div className="flex flex-col gap-3 bg-surface px-5 py-4">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-text-primary">
          {LEAGUE_LABEL[perf.league]}
        </span>
        <span className="text-[11px] text-text-tertiary">ROC-AUC</span>
      </div>
      <div className="flex items-end justify-between">
        <span className="tnum text-2xl font-semibold text-text-primary">
          {perf.training_auc != null ? perf.training_auc.toFixed(4) : "—"}
        </span>
        <div className="flex flex-col items-end gap-0.5">
          <span className="text-[10px] uppercase tracking-[0.06em] text-text-secondary">
            Logged
          </span>
          <span className="tnum text-sm text-text-secondary">{record}</span>
        </div>
      </div>
      <p className="text-[11px] leading-snug text-text-tertiary">{perf.note}</p>
    </div>
  );
}

export default async function Overview() {
  const [slates, insight, ladder, perfResults] = await Promise.all([
    settledSlates(),
    getInsight().catch(() => INSIGHT_FALLBACK),
    getLadder().catch(() => LADDER_FALLBACK),
    Promise.allSettled([getPerformance("nba"), getPerformance("mlb")]),
  ]);

  const perfs = perfResults
    .filter((r): r is PromiseFulfilledResult<Performance> => r.status === "fulfilled")
    .map((r) => r.value);

  const slateDate =
    slates.map((s) => s.slate_date).filter(Boolean).sort().at(-1) ?? null;
  const totalValue = slates.reduce((n, s) => n + s.value_count, 0);

  return (
    <div className="mx-auto max-w-[1100px] px-8 py-10">
      {/* Header */}
      <header className="flex items-end justify-between border-b border-border-subtle pb-5">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-text-primary">Overview</h1>
          <p className="mt-1 text-sm text-text-secondary">{slateDateLong(slateDate)}</p>
        </div>
        <div className="flex flex-col items-end gap-0.5">
          <span className="text-[10px] uppercase tracking-[0.06em] text-text-secondary">
            Value bets on the board
          </span>
          <span className="tnum text-lg font-semibold text-accent">{totalValue}</span>
        </div>
      </header>

      <div className="mt-8 flex flex-col gap-10">
        <AxiomRead insight={insight} />

        <LadderChallenge ladder={ladder} />

        <TopEdges slates={slates} />

        {/* Slate summary */}
        <section>
          <h3 className="pb-3 text-[11px] font-bold uppercase tracking-[0.12em] text-text-secondary">
            Slate summary
          </h3>
          <div className="grid grid-cols-1 gap-px overflow-hidden rounded-md border border-border-subtle bg-border-subtle sm:grid-cols-3">
            {slates.map((s) => (
              <LeagueSummary key={s.league} slate={s} />
            ))}
          </div>
        </section>

        {/* Performance at a glance */}
        <section>
          <h3 className="pb-3 text-[11px] font-bold uppercase tracking-[0.12em] text-text-secondary">
            Model performance
          </h3>
          <div className="grid grid-cols-1 gap-px overflow-hidden rounded-md border border-border-subtle bg-border-subtle sm:grid-cols-2">
            {perfs.map((p) => (
              <PerfGlance key={p.league} perf={p} />
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
