import type { Metadata, Viewport } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import Sidebar from "@/components/Sidebar";
import BottomNav from "@/components/BottomNav";
import ServiceWorkerManager from "@/components/ServiceWorkerManager";
import InstallPrompt from "@/components/InstallPrompt";
import PullToRefresh from "@/components/PullToRefresh";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "AXIOM Edge",
    template: "%s · AXIOM Edge",
  },
  description: "Calibrated sports-betting analytics. Not a pick. An axiom.",
  applicationName: "AXIOM Edge",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    title: "AXIOM",
    statusBarStyle: "black-translucent",
  },
};

export const viewport: Viewport = {
  themeColor: "#0A0B0D",
  colorScheme: "dark",
  // Extend under the notch / home indicator so safe-area insets can pad the shell.
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${GeistSans.variable} ${GeistMono.variable} h-full`}
    >
      <body className="min-h-full bg-bg text-text-primary">
        <div className="flex h-dvh">
          <div className="hidden md:block">
            <Sidebar />
          </div>
          <main className="flex-1 overflow-y-auto pb-[calc(4.25rem+env(safe-area-inset-bottom))] md:pb-0">
            {children}
          </main>
        </div>
        <BottomNav />
        <PullToRefresh />
        <InstallPrompt />
        <ServiceWorkerManager />
      </body>
    </html>
  );
}
