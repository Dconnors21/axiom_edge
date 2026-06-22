"use client";

import { useEffect, useMemo, useState } from "react";
import { MagnifyingGlass } from "@phosphor-icons/react";
import type { League, Research, ResearchDetail } from "@/types/api";
import { getResearch, getResearchDetail } from "@/lib/api";
import PlayerCard from "@/components/PlayerCard";

const HEADLINE: Record<League, string> = { nba: "PTS", mlb: "TB", nhl: "" };

export default function ResearchSearch({ league }: { league: League }) {
  const [q, setQ] = useState("");
  const [team, setTeam] = useState("");
  const [list, setList] = useState<Research | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<ResearchDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const t = setTimeout(() => {
      getResearch(league, q, team)
        .then((r) => !cancelled && setList(r))
        .catch(() => !cancelled && setList(null));
    }, 220);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [league, q, team]);

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setLoadingDetail(true);
    getResearchDetail(league, selected)
      .then((d) => !cancelled && setDetail(d))
      .catch(() => !cancelled && setDetail(null))
      .finally(() => !cancelled && setLoadingDetail(false));
    return () => {
      cancelled = true;
    };
  }, [league, selected]);

  const headline = HEADLINE[league];
  const leaders = useMemo(() => {
    if (!list) return [];
    return [...list.players]
      .sort((a, b) => (b.stats[headline] ?? 0) - (a.stats[headline] ?? 0))
      .slice(0, 6);
  }, [list, headline]);

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[300px_1fr]">
      {/* Left: search + results */}
      <div className="flex flex-col gap-3">
        <label className="flex items-center gap-2 rounded-[8px] border border-border-subtle bg-surface px-3 py-2.5 focus-within:border-border-strong">
          <MagnifyingGlass className="text-[16px] text-text-tertiary" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search a player"
            className="w-full bg-transparent text-sm text-text-primary outline-none placeholder:text-text-tertiary"
          />
        </label>

        <select
          value={team}
          onChange={(e) => setTeam(e.target.value)}
          className="rounded-[8px] border border-border-subtle bg-surface px-3 py-2 text-[13px] text-text-primary outline-none focus:border-border-strong"
          aria-label="Filter by team"
        >
          <option value="">All teams</option>
          {(list?.teams ?? []).map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>

        <div className="overflow-hidden rounded-md border border-border-subtle">
          {!list || list.players.length === 0 ? (
            <p className="px-4 py-6 text-center text-[13px] text-text-tertiary">No players match.</p>
          ) : (
            list.players.slice(0, 40).map((p, i) => {
              const active = selected === p.player;
              return (
                <button
                  key={p.player}
                  onClick={() => setSelected(p.player)}
                  className={`flex w-full items-center justify-between px-4 py-2.5 text-left transition-colors duration-[var(--dur-micro)] ${
                    i > 0 ? "border-t border-border-subtle" : ""
                  } ${active ? "bg-surface-elevated" : "bg-surface [@media(hover:hover)]:hover:bg-surface-elevated"}`}
                >
                  <span className="min-w-0">
                    <span className={`block truncate text-sm ${active ? "text-accent" : "text-text-primary"}`}>
                      {p.player}
                    </span>
                    <span className="text-[11px] text-text-tertiary">{p.team}</span>
                  </span>
                  {headline && (
                    <span className="tnum text-[13px] text-text-secondary">
                      {(p.stats[headline] ?? 0).toFixed(1)} {headline}
                    </span>
                  )}
                </button>
              );
            })
          )}
        </div>
      </div>

      {/* Right: focused player or prompt + leaders */}
      <div>
        {detail && detail.found ? (
          <PlayerCard key={detail.player} detail={detail} />
        ) : loadingDetail ? (
          <div className="rounded-md border border-border-subtle bg-surface px-6 py-10 text-sm text-text-tertiary">
            Loading…
          </div>
        ) : (
          <div className="rounded-md border border-border-subtle bg-surface px-6 py-8">
            <p className="text-sm text-text-secondary">Pick a player to see recent form, or start with a leader:</p>
            <div className="mt-4 flex flex-wrap gap-2">
              {leaders.map((p) => (
                <button
                  key={p.player}
                  onClick={() => setSelected(p.player)}
                  className="flex items-center gap-2 rounded-full border border-border-subtle bg-surface-elevated px-3 py-1.5 text-[13px] text-text-primary transition-transform duration-[var(--dur-micro)] [@media(hover:hover)]:hover:border-border-strong active:scale-[0.97]"
                >
                  {p.player}
                  {headline && (
                    <span className="tnum text-text-tertiary">
                      {(p.stats[headline] ?? 0).toFixed(1)}
                    </span>
                  )}
                </button>
              ))}
            </div>
            <p className="mt-5 text-[11px] text-text-tertiary">
              Leaders ranked by {headline || "recent form"} over their last 10 games.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
