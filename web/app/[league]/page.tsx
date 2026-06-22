import type { Metadata } from "next";
import { notFound } from "next/navigation";
import type { League } from "@/types/api";
import { getSlate } from "@/lib/api";
import { slateDateLong, signedPct } from "@/lib/format";
import StatBlock from "@/components/StatBlock";
import SlateTable from "@/components/SlateTable";

export const dynamic = "force-dynamic";

const LEAGUES: League[] = ["nba", "mlb", "nhl"];
const LABEL: Record<League, string> = { nba: "NBA", mlb: "MLB", nhl: "NHL" };

function isLeague(v: string): v is League {
  return (LEAGUES as string[]).includes(v);
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ league: string }>;
}): Promise<Metadata> {
  const { league } = await params;
  if (!isLeague(league)) return { title: "Not found" };
  return { title: `${LABEL[league]} Picks` };
}

export default async function LeaguePicks({
  params,
}: {
  params: Promise<{ league: string }>;
}) {
  const { league } = await params;
  if (!isLeague(league)) notFound();

  const slate = await getSlate(league);

  return (
    <div className="mx-auto max-w-[1100px] px-8 py-10">
      <header className="flex items-end justify-between border-b border-border-subtle pb-5">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-text-primary">
            {LABEL[league]} Today&apos;s Picks
          </h1>
          <p className="mt-1 text-sm text-text-secondary">{slateDateLong(slate.slate_date)}</p>
        </div>
      </header>

      {slate.game_count === 0 ? (
        <div className="mt-10 rounded-md border border-border-subtle bg-surface px-6 py-10 text-center">
          <p className="text-sm text-text-secondary">
            No {LABEL[league]} games on the board.
          </p>
          <p className="mt-1 text-[13px] text-text-tertiary">
            The model runs when there is a slate. Check back on game day.{" "}
            <span className="text-accent">∎</span>
          </p>
        </div>
      ) : (
        <div className="mt-8 flex flex-col gap-8">
          <div className="grid grid-cols-3 gap-x-10">
            <StatBlock label="Games" value={String(slate.game_count)} />
            <StatBlock label="Value bets" value={String(slate.value_count)} tone="accent" />
            <StatBlock
              label="Best edge"
              value={slate.best_edge > 0 ? signedPct(slate.best_edge) : "—"}
              tone="pos"
            />
          </div>

          <section>
            <h3 className="pb-3 text-[11px] font-bold uppercase tracking-[0.12em] text-text-secondary">
              Moneyline
            </h3>
            <SlateTable games={slate.games} />
          </section>
        </div>
      )}
    </div>
  );
}
