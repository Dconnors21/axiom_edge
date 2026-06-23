import type { Ladder } from "@/types/api";
import { pct, signedPct, odds, money } from "@/lib/format";

const LEAGUE_LABEL: Record<string, string> = { nba: "NBA", mlb: "MLB", nhl: "NHL" };

function Header() {
  return (
    <div className="flex items-baseline justify-between">
      <div>
        <h3 className="text-[11px] font-bold uppercase tracking-[0.12em] text-accent">
          Ladder Challenge
        </h3>
        <p className="mt-1 text-[13px] text-text-secondary">
          One high-conviction play, near +100. Win and let it ride for a 7–10 day run.
        </p>
      </div>
      <span className="text-2xl leading-none text-accent">∎</span>
    </div>
  );
}

export default function LadderChallenge({ ladder }: { ladder: Ladder }) {
  if (!ladder.available) {
    return (
      <section className="rounded-md border border-border-strong bg-surface-elevated px-6 py-6">
        <Header />
        <p className="mt-4 text-sm text-text-secondary">
          {ladder.reason || "No qualifying ladder on the board today."}
        </p>
      </section>
    );
  }

  const prob = ladder.combined_model_prob ?? 0;
  const days = ladder.target_days;
  // Milestone rungs: balance grows, survival shrinks — the honest tension.
  const milestones = [1, Math.round(days / 2.5), Math.round(days * 0.7), days]
    .filter((d, i, a) => d >= 1 && d <= days && a.indexOf(d) === i);

  return (
    <section className="rounded-md border border-border-strong bg-surface-elevated px-6 py-6">
      <Header />

      {/* Today's play */}
      <div className="mt-5 overflow-hidden rounded-md border border-border-subtle">
        {ladder.legs.map((l, i) => (
          <div
            key={`${l.selection}-${i}`}
            className={`flex items-center justify-between bg-surface px-4 py-3 ${
              i > 0 ? "border-t border-border-subtle" : ""
            }`}
          >
            <div className="min-w-0">
              <div className="truncate text-sm font-medium text-text-primary">{l.selection}</div>
              <div className="truncate text-[11px] text-text-tertiary">
                {LEAGUE_LABEL[l.league]} {l.market} · {l.matchup}
              </div>
            </div>
            <div className="flex items-center gap-5">
              <span className="tnum text-sm text-text-secondary">{pct(l.model_prob)}</span>
              <span className="tnum w-12 text-right text-sm text-text-primary">{odds(l.price)}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Combined line + stake math */}
      <div className="mt-4 grid grid-cols-2 gap-x-8 gap-y-4 sm:grid-cols-4">
        <div className="flex flex-col gap-1">
          <span className="text-[10px] uppercase tracking-[0.06em] text-text-secondary">Combined</span>
          <span className="tnum text-lg font-semibold text-accent">{odds(ladder.combined_american)}</span>
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-[10px] uppercase tracking-[0.06em] text-text-secondary">Model prob</span>
          <span className="tnum text-lg font-semibold text-text-primary">{pct(prob)}</span>
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-[10px] uppercase tracking-[0.06em] text-text-secondary">Edge</span>
          <span className="tnum text-lg font-semibold text-pos">{signedPct(ladder.edge ?? 0)}</span>
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-[10px] uppercase tracking-[0.06em] text-text-secondary">
            {money(ladder.stake)} returns
          </span>
          <span className="tnum text-lg font-semibold text-text-primary">{money(ladder.payout ?? 0)}</span>
        </div>
      </div>

      {/* The run: balance climbs, survival falls */}
      <div className="mt-6">
        <div className="flex items-baseline justify-between pb-2">
          <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-text-tertiary">
            The run · let it ride
          </span>
          <span className="text-[11px] text-text-tertiary">from {money(ladder.stake)}</span>
        </div>
        <div className="grid grid-cols-4 gap-px overflow-hidden rounded-md border border-border-subtle bg-border-subtle">
          {milestones.map((d) => {
            const bal = ladder.projection[d - 1]?.balance ?? 0;
            const survive = Math.pow(prob, d) * 100;
            return (
              <div key={d} className="flex flex-col gap-1 bg-surface px-4 py-3">
                <span className="text-[10px] uppercase tracking-[0.06em] text-text-secondary">
                  Day {d}
                </span>
                <span className="tnum text-base font-semibold text-text-primary">{money(bal)}</span>
                <span className="tnum text-[11px] text-text-tertiary">{survive.toFixed(1)}% to here</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Honest reality + responsible framing */}
      <p className="mt-4 text-[11px] leading-relaxed text-text-tertiary">
        Compounding is unforgiving: one loss ends the run.{" "}
        <span className="tnum text-text-secondary">{(ladder.survival_7 ?? 0).toFixed(1)}%</span> of runs
        reach day 7,{" "}
        <span className="tnum text-text-secondary">{(ladder.survival_10 ?? 0).toFixed(1)}%</span> reach
        day 10. For analysis only. Size stakes you can afford to lose.
      </p>
    </section>
  );
}
