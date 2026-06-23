"use client";

import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8001";
const LEAGUES = ["nba", "mlb", "nhl"] as const;

type Prefs = {
  threshold: number;
  leagues: string[];
  quiet_start: number;
  quiet_end: number;
  daily_cap: number;
};

const DEFAULT_PREFS: Prefs = {
  threshold: 0.05,
  leagues: ["nba", "mlb", "nhl"],
  quiet_start: 23,
  quiet_end: 8,
  daily_cap: 3,
};

function urlBase64ToUint8Array(base64: string): Uint8Array {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const b64 = (base64 + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(b64);
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

const isIOS = () =>
  /iphone|ipad|ipod/i.test(navigator.userAgent) ||
  (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
const isStandalone = () =>
  window.matchMedia("(display-mode: standalone)").matches ||
  // @ts-expect-error iOS-only
  navigator.standalone === true;

const hour = (h: number) => `${((h + 11) % 12) + 1}${h < 12 ? "am" : "pm"}`;

export default function PushSettings() {
  const [perm, setPerm] = useState<NotificationPermission | "unsupported">("default");
  const [endpoint, setEndpoint] = useState<string | null>(null);
  const [needsInstall, setNeedsInstall] = useState(false);
  const [busy, setBusy] = useState(false);
  const [prefs, setPrefs] = useState<Prefs>(DEFAULT_PREFS);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!("Notification" in window) || !("serviceWorker" in navigator)) {
      setPerm("unsupported");
      return;
    }
    setPerm(Notification.permission);
    if (isIOS() && !isStandalone()) setNeedsInstall(true);
    navigator.serviceWorker.ready
      .then((reg) => reg.pushManager.getSubscription())
      .then((sub) => sub && setEndpoint(sub.endpoint))
      .catch(() => {});
  }, []);

  async function enable() {
    setBusy(true);
    try {
      const res = await Notification.requestPermission();
      setPerm(res);
      if (res !== "granted") return;
      const reg = await navigator.serviceWorker.ready;
      const { public_key } = await fetch(`${API}/api/push/vapid`).then((r) => r.json());
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(public_key) as BufferSource,
      });
      await fetch(`${API}/api/push/subscribe`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          subscription: sub.toJSON(),
          prefs: { ...prefs, leagues: prefs.leagues.join(",") },
        }),
      });
      setEndpoint(sub.endpoint);
      await fetch(`${API}/api/push/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ endpoint: sub.endpoint }),
      });
    } finally {
      setBusy(false);
    }
  }

  async function save(next: Prefs) {
    setPrefs(next);
    if (!endpoint) return;
    await fetch(`${API}/api/push/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ endpoint, prefs: { ...next, leagues: next.leagues.join(",") } }),
    });
  }

  async function disable() {
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    if (sub) {
      await fetch(`${API}/api/push/unsubscribe`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ endpoint: sub.endpoint }),
      });
      await sub.unsubscribe();
    }
    setEndpoint(null);
  }

  // ── States ──────────────────────────────────────────────────────────────
  if (perm === "unsupported") {
    return (
      <p className="rounded-md border border-border-subtle bg-surface px-5 py-6 text-sm text-text-secondary">
        This browser doesn&apos;t support push notifications.
      </p>
    );
  }

  if (needsInstall && !endpoint) {
    return (
      <div className="rounded-md border border-border-subtle bg-surface px-5 py-6">
        <h3 className="text-sm font-semibold text-text-primary">Add AXIOM to your Home Screen first</h3>
        <p className="mt-2 text-[13px] leading-relaxed text-text-secondary">
          On iPhone, push alerts only work from an installed app. In Safari, tap Share, then
          &ldquo;Add to Home Screen,&rdquo; and open AXIOM from the new icon. Then come back here to
          enable alerts. <span className="text-accent">∎</span>
        </p>
      </div>
    );
  }

  if (!endpoint) {
    // Primer: explain before asking for permission.
    return (
      <div className="rounded-md border border-border-strong bg-surface-elevated px-6 py-6">
        <h3 className="text-sm font-semibold text-text-primary">Edge alerts</h3>
        <p className="mt-2 max-w-prose text-[13px] leading-relaxed text-text-secondary">
          We&apos;ll notify you when the model flags an edge that clears your threshold. Informational
          only, no hype. You control the threshold, leagues, quiet hours, and a daily cap, and you can
          turn it off anytime.
        </p>
        {perm === "denied" ? (
          <p className="mt-4 text-[13px] text-neg">
            Notifications are blocked. Re-enable them for this site in your browser settings.
          </p>
        ) : (
          <button
            onClick={enable}
            disabled={busy}
            className="mt-4 rounded-[8px] bg-accent px-4 py-2 text-sm font-medium text-bg transition-transform duration-[var(--dur-micro)] active:scale-[0.97] disabled:opacity-60"
          >
            {busy ? "Enabling…" : "Enable alerts"}
          </button>
        )}
      </div>
    );
  }

  // Subscribed: show controls.
  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between rounded-md border border-border-subtle bg-surface px-5 py-3">
        <span className="inline-flex items-center gap-2 text-sm text-text-primary">
          <span className="h-2 w-2 rounded-full bg-pos" /> Alerts on
        </span>
        <button
          onClick={disable}
          className="text-[13px] text-text-secondary transition-colors [@media(hover:hover)]:hover:text-neg"
        >
          Turn off
        </button>
      </div>

      <Row label="Edge threshold" hint="Minimum model edge to notify on.">
        <select
          value={prefs.threshold}
          onChange={(e) => save({ ...prefs, threshold: Number(e.target.value) })}
          className="rounded-[8px] border border-border-subtle bg-surface px-3 py-2 text-[13px] text-text-primary outline-none focus:border-border-strong"
        >
          {[0.03, 0.04, 0.05, 0.07, 0.1].map((t) => (
            <option key={t} value={t}>{`${(t * 100).toFixed(0)}%`}</option>
          ))}
        </select>
      </Row>

      <Row label="Leagues" hint="Which slates can alert you.">
        <div className="flex gap-1.5">
          {LEAGUES.map((lg) => {
            const on = prefs.leagues.includes(lg);
            return (
              <button
                key={lg}
                onClick={() =>
                  save({
                    ...prefs,
                    leagues: on ? prefs.leagues.filter((x) => x !== lg) : [...prefs.leagues, lg],
                  })
                }
                className={`rounded-[8px] px-3 py-1.5 text-[12px] font-medium uppercase tracking-[0.06em] transition-colors duration-[var(--dur-micro)] ${
                  on
                    ? "bg-surface-elevated text-accent"
                    : "bg-surface text-text-tertiary [@media(hover:hover)]:hover:text-text-secondary"
                }`}
              >
                {lg}
              </button>
            );
          })}
        </div>
      </Row>

      <Row label="Quiet hours" hint="No alerts during this window (ET).">
        <div className="flex items-center gap-2 text-[13px] text-text-secondary">
          <HourSelect value={prefs.quiet_start} onChange={(v) => save({ ...prefs, quiet_start: v })} />
          <span>to</span>
          <HourSelect value={prefs.quiet_end} onChange={(v) => save({ ...prefs, quiet_end: v })} />
        </div>
      </Row>

      <Row label="Daily cap" hint="Most alerts per day.">
        <select
          value={prefs.daily_cap}
          onChange={(e) => save({ ...prefs, daily_cap: Number(e.target.value) })}
          className="rounded-[8px] border border-border-subtle bg-surface px-3 py-2 text-[13px] text-text-primary outline-none focus:border-border-strong"
        >
          {[1, 2, 3, 5].map((n) => (
            <option key={n} value={n}>{n}</option>
          ))}
        </select>
      </Row>
    </div>
  );
}

function Row({ label, hint, children }: { label: string; hint: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-6 border-b border-border-subtle pb-4">
      <div>
        <div className="text-sm text-text-primary">{label}</div>
        <div className="text-[12px] text-text-tertiary">{hint}</div>
      </div>
      {children}
    </div>
  );
}

function HourSelect({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(Number(e.target.value))}
      className="rounded-[8px] border border-border-subtle bg-surface px-2.5 py-1.5 text-[13px] text-text-primary outline-none focus:border-border-strong"
    >
      {Array.from({ length: 24 }, (_, h) => (
        <option key={h} value={h}>{hour(h)}</option>
      ))}
    </select>
  );
}
