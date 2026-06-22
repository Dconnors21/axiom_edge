import type { Metadata } from "next";
import { notFound } from "next/navigation";
import type { League, Side } from "@/types/api";
import { getSlate } from "@/lib/api";
import { pct, signedPct, odds, americanToDecimal, decimalToAmerican } from "@/lib/format";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "NBA Parlay Builder" };

type Leg = { team: string; matchup: string; prob: number; edge: number; price: number };

// Parlay builder lives on NBA only in the current IA.
export default async function ParlayPage({ params }: { params: Promise<{ league: string }> }) {
  const { league } = await params;
  if (league !== "nba") notFound();

  const slate = await getSlate(league as League);

  const legs: Leg[] = [];
  for (const g of slate.games) {
    const side: Side | null = g.home.is_value ? g.home : g.away.is_value ? g.away : null;
    if (side && side.price != null) {
      legs.push({
        team: side.team,
        matchup: `${g.away_team} @ ${g.home_team}`,
        prob: side.model_prob,
        edge: side.edge,
        price: side.price,
      });
    }
  }
  legs.sort((a, b) => b.edge - a.edge);
  const picked = legs.slice(0, 4);

  const decimal = picked.reduce((acc, l) => acc * americanToDecimal(l.price), 1);
  const prob = picked.reduce((acc, l) => acc * l.prob, 1);
  const ev = prob * decimal - 1;

  return (
    <div className="mx-auto max-w-[1100px] px-8 py-10">
      <header className="border-b border-border-subtle pb-5">
        <h1 className="text-xl font-semibold tracking-tight text-text-primary">
          NBA Parlay Builder
        </h1>
        <p className="mt-1 text-sm text-text-secondary">
          Joint odds from today&apos;s value legs, assuming independence.
        </p>
      </header>

      {picked.length < 2 ? (
        <div className="mt-10 rounded-md border border-border-subtle bg-surface px-6 py-10 text-center">
          <p className="text-sm text-text-secondary">
            Need at least two value legs to build a parlay. Today&apos;s board has {legs.length}.
          </p>
          <p className="mt-1 text-[13px] text-text-tertiary">
            Correlated and thin slates are skipped on purpose. <span className="text-accent">∎</span>
          </p>
        </div>
      ) : (
        <div className="mt-8 grid grid-cols-1 gap-px overflow-hidden rounded-md border border-border-subtle bg-border-subtle lg:grid-cols-[1fr_320px]">
          {/* Legs */}
          <div className="bg-surface">
            <div className="border-b border-border-subtle px-5 py-2.5 text-[10px] font-semibold uppercase tracking-[0.06em] text-text-tertiary">
              {picked.length} legs
            </div>
            {picked.map((l, i) => (
              <div
                key={`${l.team}-${i}`}
                className={`flex items-center justify-between px-5 py-3 ${
                  i > 0 ? "border-t border-border-subtle" : ""
                }`}
              >
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium text-text-primary">{l.team}</div>
                  <div className="truncate text-[11px] text-text-tertiary">{l.matchup}</div>
                </div>
                <div className="flex items-center gap-5">
                  <span className="tnum text-sm text-text-secondary">{pct(l.prob)}</span>
                  <span className="tnum text-sm font-semibold text-pos">{signedPct(l.edge)}</span>
                  <span className="tnum w-12 text-right text-sm text-text-secondary">{odds(l.price)}</span>
                </div>
              </div>
            ))}
          </div>

          {/* Combined */}
          <div className="flex flex-col gap-4 bg-surface px-6 py-5">
            <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-accent">
              Combined parlay
            </div>
            <div>
              <div className="text-[11px] uppercase tracking-[0.06em] text-text-secondary">
                Joint odds
              </div>
              <div className="tnum mt-1 text-3xl font-semibold text-text-primary">
                {odds(decimalToAmerican(decimal))}
              </div>
              <div className="tnum mt-0.5 text-[12px] text-text-tertiary">
                {decimal.toFixed(2)} decimal
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4 border-t border-border-subtle pt-4">
              <div className="flex flex-col gap-1">
                <span className="text-[11px] uppercase tracking-[0.06em] text-text-secondary">
                  Model prob
                </span>
                <span className="tnum text-lg font-semibold text-text-primary">{pct(prob)}</span>
              </div>
              <div className="flex flex-col gap-1">
                <span className="text-[11px] uppercase tracking-[0.06em] text-text-secondary">
                  EV / unit
                </span>
                <span className={`tnum text-lg font-semibold ${ev >= 0 ? "text-pos" : "text-neg"}`}>
                  {signedPct(ev)}
                </span>
              </div>
            </div>
            <p className="text-[11px] leading-snug text-text-tertiary">
              Parlays multiply variance. Independence is assumed; correlated legs inflate the
              true probability.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
