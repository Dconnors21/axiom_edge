import type { Metadata } from "next";
import { notFound } from "next/navigation";
import type { League } from "@/types/api";
import ResearchSearch from "@/components/ResearchSearch";

export const metadata: Metadata = { title: "Player Research" };

const LABEL: Record<string, string> = { nba: "NBA", mlb: "MLB" };

export default async function ResearchPage({ params }: { params: Promise<{ league: string }> }) {
  const { league } = await params;
  if (league !== "nba" && league !== "mlb") notFound();

  return (
    <div className="mx-auto max-w-[1100px] px-8 py-10">
      <header className="border-b border-border-subtle pb-5">
        <h1 className="text-xl font-semibold tracking-tight text-text-primary">
          {LABEL[league]} Player Research
        </h1>
        <p className="mt-1 text-sm text-text-secondary">Recent form from game logs.</p>
      </header>

      <div className="mt-8">
        <ResearchSearch league={league as League} />
      </div>
    </div>
  );
}
