import type { StationArrivalsResponse } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function fetchStationArrivals(
  stationId: number | string,
  route?: string,
  n = 8
): Promise<StationArrivalsResponse> {
  const params = new URLSearchParams({ n: String(n) });
  if (route) params.set("route", route);

  const res = await fetch(
    `${BASE}/stations/${stationId}/arrivals?${params}`,
    { next: { revalidate: 20 } }
  );

  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${await res.text()}`);
  }
  return res.json();
}
