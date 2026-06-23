import type { Metadata } from "next";
import PushSettings from "@/components/PushSettings";

export const metadata: Metadata = { title: "Settings" };

export default function SettingsPage() {
  return (
    <div className="mx-auto max-w-[760px] px-8 py-10">
      <header className="border-b border-border-subtle pb-5">
        <h1 className="text-xl font-semibold tracking-tight text-text-primary">Settings</h1>
        <p className="mt-1 text-sm text-text-secondary">Alerts and notifications.</p>
      </header>

      <section className="mt-8">
        <h2 className="pb-4 text-[11px] font-bold uppercase tracking-[0.12em] text-text-secondary">
          Push notifications
        </h2>
        <PushSettings />
      </section>

      <p className="mt-10 border-t border-border-subtle pt-5 text-[11px] leading-relaxed text-text-tertiary">
        AXIOM Edge is for analysis. It does not place bets or move money. If betting stops being
        fun, take a break. Help is available at 1-800-GAMBLER. <span className="text-accent">∎</span>
      </p>
    </div>
  );
}
