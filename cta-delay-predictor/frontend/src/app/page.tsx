"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import StationSearch from "@/components/StationSearch";
import { RED_LINE_STATIONS, BLUE_LINE_STATIONS } from "@/lib/types";

export default function Home() {
  const router = useRouter();
  const [activeLine, setActiveLine] = useState<"Red" | "Blue">("Red");

  const stations = activeLine === "Red" ? RED_LINE_STATIONS : BLUE_LINE_STATIONS;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold mb-1">Station Arrivals</h1>
        <p className="text-gray-400 text-sm">
          Select a station to see upcoming trains with schedule deviation
          estimates.
        </p>
      </div>

      {/* Line toggle */}
      <div className="flex gap-2">
        <button
          type="button"
          aria-pressed={activeLine === "Red"}
          onClick={() => setActiveLine("Red")}
          className={`inline-flex items-center justify-center min-h-[44px] px-4 py-1.5 rounded-full text-sm font-semibold transition-colors ${
            activeLine === "Red"
              ? "bg-[#c60c30] text-white"
              : "bg-gray-800 text-gray-300 hover:bg-gray-700"
          }`}
        >
          Red Line
        </button>
        <button
          type="button"
          aria-pressed={activeLine === "Blue"}
          onClick={() => setActiveLine("Blue")}
          className={`inline-flex items-center justify-center min-h-[44px] px-4 py-1.5 rounded-full text-sm font-semibold transition-colors ${
            activeLine === "Blue"
              ? "bg-[#00a1de] text-white"
              : "bg-gray-800 text-gray-300 hover:bg-gray-700"
          }`}
        >
          Blue Line
        </button>
      </div>

      <StationSearch
        stations={stations}
        onSelect={(s) => router.push(`/stations/${s.mapid}?route=${s.route}`)}
      />

      {/* Quick-pick grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
        {stations.map((s) => (
          <button
            key={s.mapid}
            type="button"
            onClick={() => router.push(`/stations/${s.mapid}?route=${s.route}`)}
            className="flex items-center min-h-[44px] text-left px-3 py-2 rounded-lg bg-gray-900 hover:bg-gray-800 border border-gray-800 hover:border-gray-600 transition-colors text-sm"
          >
            <span className="truncate">{s.name}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
