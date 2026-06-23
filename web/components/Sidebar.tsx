"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  House,
  Wallet,
  ChartLineUp,
  Basketball,
  Baseball,
  Hockey,
  Gear,
} from "@phosphor-icons/react";

type NavItem = { label: string; href: string };
type NavGroup = { heading?: string; icon?: React.ReactNode; items: NavItem[] };

// Information architecture preserved 1:1 from the Streamlit app (13 destinations).
const GROUPS: NavGroup[] = [
  {
    items: [
      { label: "Overview", href: "/" },
      { label: "Bankroll", href: "/bankroll" },
      { label: "Model Performance", href: "/performance" },
      { label: "Settings", href: "/settings" },
    ],
  },
  {
    heading: "NBA",
    icon: <Basketball weight="fill" />,
    items: [
      { label: "Today's Picks", href: "/nba" },
      { label: "ROI Tracker", href: "/nba/roi" },
      { label: "Parlay Builder", href: "/nba/parlay" },
      { label: "Player Research", href: "/nba/research" },
    ],
  },
  {
    heading: "MLB",
    icon: <Baseball weight="fill" />,
    items: [
      { label: "Today's Picks", href: "/mlb" },
      { label: "Player Props", href: "/mlb/props" },
      { label: "ROI Tracker", href: "/mlb/roi" },
      { label: "Player Research", href: "/mlb/research" },
    ],
  },
  {
    heading: "NHL",
    icon: <Hockey weight="fill" />,
    items: [
      { label: "Today's Picks", href: "/nhl" },
      { label: "ROI Tracker", href: "/nhl/roi" },
    ],
  },
];

const TOP_ICONS: Record<string, React.ReactNode> = {
  "/": <House weight="fill" />,
  "/bankroll": <Wallet weight="fill" />,
  "/performance": <ChartLineUp weight="fill" />,
  "/settings": <Gear weight="fill" />,
};

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <nav className="flex h-full w-60 shrink-0 flex-col gap-6 border-r border-border-subtle bg-bg px-3 py-5">
      {/* Wordmark */}
      <Link href="/" className="flex items-baseline gap-1.5 px-2">
        <span className="text-lg font-semibold tracking-tight text-text-primary">
          AXIOM
        </span>
        <span className="text-lg leading-none text-accent">∎</span>
      </Link>

      <div className="flex flex-col gap-5">
        {GROUPS.map((group, gi) => (
          <div key={group.heading ?? gi} className="flex flex-col gap-0.5">
            {group.heading && (
              <div className="flex items-center gap-1.5 px-2 pb-1.5 text-[10px] font-bold uppercase tracking-[0.14em] text-text-tertiary">
                <span className="text-[13px] text-text-tertiary">{group.icon}</span>
                {group.heading}
              </div>
            )}
            {group.items.map((item) => {
              const active = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={`flex items-center gap-2 rounded-[8px] px-2 py-1.5 text-[13px] transition-colors duration-[var(--dur-micro)] ${
                    active
                      ? "bg-surface-elevated font-medium text-accent"
                      : "text-text-secondary hover:bg-surface hover:text-text-primary"
                  }`}
                >
                  {group.heading ? (
                    <span className="w-[13px]" />
                  ) : (
                    <span className="text-[15px]">{TOP_ICONS[item.href]}</span>
                  )}
                  {item.label}
                </Link>
              );
            })}
          </div>
        ))}
      </div>
    </nav>
  );
}
