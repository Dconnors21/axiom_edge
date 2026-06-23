import type {
  League,
  Slate,
  Insight,
  Performance,
  Roi,
  PropsSlate,
  Research,
  ResearchDetail,
  Ladder,
  EVRequest,
  EVResponse,
} from "@/types/api";

const BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

// Live odds/EV are perishable — never cache them at the data layer.
// (PWA addendum enforces the same rule in the service worker.)
async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${path} -> ${res.status}`);
  return res.json() as Promise<T>;
}

export const getSlate = (league: League) => get<Slate>(`/api/slate/${league}`);
export const getInsight = () => get<Insight>("/api/insight");
export const getLadder = (stake = 50, days = 10) =>
  get<Ladder>(`/api/ladder?stake=${stake}&days=${days}`);
export const getPerformance = (league: League) =>
  get<Performance>(`/api/performance/${league}`);
export const getRoi = (league: League) => get<Roi>(`/api/roi/${league}`);
export const getProps = (league: League) => get<PropsSlate>(`/api/props/${league}`);
export const getResearch = (league: League, q: string, team = "") =>
  get<Research>(
    `/api/research/${league}?q=${encodeURIComponent(q)}&team=${encodeURIComponent(team)}`,
  );
export const getResearchDetail = (league: League, name: string) =>
  get<ResearchDetail>(`/api/research/${league}/player?name=${encodeURIComponent(name)}`);

export async function postEv(body: EVRequest): Promise<EVResponse> {
  const res = await fetch(`${BASE}/api/ev`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`API /api/ev -> ${res.status}`);
  return res.json() as Promise<EVResponse>;
}
