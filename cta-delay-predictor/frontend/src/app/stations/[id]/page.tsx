import { Suspense } from "react";
import { fetchStationArrivals } from "@/lib/api";
import StationBoard from "@/components/StationBoard";
import Link from "next/link";

interface Props {
  params: { id: string };
  searchParams: { route?: string };
}

export default async function StationPage({ params, searchParams }: Props) {
  const { id } = params;
  const route = searchParams.route;

  let data = null;
  let error: string | null = null;

  try {
    data = await fetchStationArrivals(id, route);
  } catch (e: unknown) {
    error = e instanceof Error ? e.message : "Failed to load arrivals";
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Link href="/" className="text-gray-400 hover:text-white text-sm">
          ← All stations
        </Link>
      </div>

      {error ? (
        <div className="rounded-lg bg-red-950 border border-red-800 p-4 text-red-300 text-sm">
          {error}
        </div>
      ) : data ? (
        <Suspense fallback={<p className="text-gray-500">Loading…</p>}>
          <StationBoard data={data} />
        </Suspense>
      ) : (
        <p className="text-gray-500">Loading…</p>
      )}
    </div>
  );
}
