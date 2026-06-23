"use client";

import { useEffect, useState } from "react";
import { X } from "@phosphor-icons/react";

const DISMISS_KEY = "axiom-install-dismissed";

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: string }>;
}

export default function InstallPrompt() {
  const [deferred, setDeferred] = useState<BeforeInstallPromptEvent | null>(null);
  const [show, setShow] = useState(false);
  const [iosHint, setIosHint] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (localStorage.getItem(DISMISS_KEY)) return;
    const standalone =
      window.matchMedia("(display-mode: standalone)").matches ||
      // @ts-expect-error iOS-only
      navigator.standalone === true;
    if (standalone) return;

    const ua = navigator.userAgent;
    const isIOS = /iphone|ipad|ipod/i.test(ua);
    const isSafari = /^((?!chrome|android|crios|fxios).)*safari/i.test(ua);
    if (isIOS && isSafari) {
      // Don't nag on first paint — surface after a moment.
      const t = setTimeout(() => {
        setIosHint(true);
        setShow(true);
      }, 4000);
      return () => clearTimeout(t);
    }

    const handler = (e: Event) => {
      e.preventDefault();
      setDeferred(e as BeforeInstallPromptEvent);
      setShow(true);
    };
    window.addEventListener("beforeinstallprompt", handler);
    return () => window.removeEventListener("beforeinstallprompt", handler);
  }, []);

  function dismiss() {
    localStorage.setItem(DISMISS_KEY, "1");
    setShow(false);
  }

  async function install() {
    if (!deferred) return;
    await deferred.prompt();
    await deferred.userChoice;
    setDeferred(null);
    setShow(false);
  }

  if (!show) return null;

  return (
    <div className="fixed inset-x-0 z-30 bottom-[calc(4.75rem+env(safe-area-inset-bottom))] px-4 md:inset-x-auto md:bottom-4 md:right-4 md:w-80">
      <div className="flex items-center gap-3 rounded-md border border-border-strong bg-surface-overlay px-4 py-3 shadow-lg">
        <span className="text-lg leading-none text-accent">∎</span>
        <p className="min-w-0 flex-1 text-[13px] text-text-secondary">
          {iosHint
            ? "Install AXIOM: tap Share, then “Add to Home Screen.”"
            : "Install AXIOM for instant access and edge alerts."}
        </p>
        {!iosHint && (
          <button
            onClick={install}
            className="rounded-[8px] bg-accent px-3 py-1.5 text-[13px] font-medium text-bg transition-transform duration-[var(--dur-micro)] active:scale-[0.97]"
          >
            Install
          </button>
        )}
        <button onClick={dismiss} aria-label="Dismiss">
          <X className="text-[16px] text-text-tertiary" />
        </button>
      </div>
    </div>
  );
}
