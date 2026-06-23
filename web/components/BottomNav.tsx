"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  House,
  Basketball,
  Baseball,
  Hockey,
  DotsThreeOutline,
  Wallet,
  ChartLineUp,
  Gear,
  X,
} from "@phosphor-icons/react";

const TABS = [
  { label: "Today", href: "/", Icon: House },
  { label: "NBA", href: "/nba", Icon: Basketball },
  { label: "MLB", href: "/mlb", Icon: Baseball },
  { label: "NHL", href: "/nhl", Icon: Hockey },
];

const MORE = [
  { label: "Bankroll", href: "/bankroll", Icon: Wallet },
  { label: "Model Performance", href: "/performance", Icon: ChartLineUp },
  { label: "Settings", href: "/settings", Icon: Gear },
];

export default function BottomNav() {
  const pathname = usePathname();
  const [sheet, setSheet] = useState(false);

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
  const moreActive = MORE.some((m) => isActive(m.href));

  return (
    <>
      {/* More sheet */}
      {sheet && (
        <div className="fixed inset-0 z-40 md:hidden" onClick={() => setSheet(false)}>
          <div className="absolute inset-0 bg-black/50" />
          <div
            className="absolute inset-x-0 bottom-0 rounded-t-md border-t border-border-strong bg-surface-overlay pb-[calc(4.5rem+env(safe-area-inset-bottom))] pt-2"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-5 py-2">
              <span className="text-[11px] font-bold uppercase tracking-[0.12em] text-text-tertiary">
                More
              </span>
              <button onClick={() => setSheet(false)} aria-label="Close">
                <X className="text-[18px] text-text-secondary" />
              </button>
            </div>
            {MORE.map((m) => (
              <Link
                key={m.href}
                href={m.href}
                onClick={() => setSheet(false)}
                className={`flex items-center gap-3 px-5 py-3 text-sm ${
                  isActive(m.href) ? "text-accent" : "text-text-primary"
                }`}
              >
                <m.Icon weight="fill" className="text-[18px]" />
                {m.label}
              </Link>
            ))}
          </div>
        </div>
      )}

      <nav className="fixed inset-x-0 bottom-0 z-30 flex border-t border-border-subtle bg-bg pb-[env(safe-area-inset-bottom)] md:hidden">
        {TABS.map((t) => {
          const active = isActive(t.href);
          return (
            <Link
              key={t.href}
              href={t.href}
              className="flex flex-1 flex-col items-center gap-1 py-2.5"
              aria-current={active ? "page" : undefined}
            >
              <t.Icon weight={active ? "fill" : "regular"} className={`text-[20px] ${active ? "text-accent" : "text-text-tertiary"}`} />
              <span className={`text-[10px] ${active ? "text-accent" : "text-text-tertiary"}`}>{t.label}</span>
            </Link>
          );
        })}
        <button
          onClick={() => setSheet((s) => !s)}
          className="flex flex-1 flex-col items-center gap-1 py-2.5"
        >
          <DotsThreeOutline weight={moreActive || sheet ? "fill" : "regular"} className={`text-[20px] ${moreActive || sheet ? "text-accent" : "text-text-tertiary"}`} />
          <span className={`text-[10px] ${moreActive || sheet ? "text-accent" : "text-text-tertiary"}`}>More</span>
        </button>
      </nav>
    </>
  );
}
