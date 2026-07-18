"use client";

import { useState } from "react";
import type { Station } from "@/lib/types";

interface Props {
  stations: Station[];
  onSelect: (station: Station) => void;
}

export default function StationSearch({ stations, onSelect }: Props) {
  const [query, setQuery] = useState("");

  const results =
    query.length >= 1
      ? stations.filter((s) =>
          s.name.toLowerCase().includes(query.toLowerCase())
        )
      : [];

  return (
    <div className="relative">
      <input
        type="text"
        aria-label="Search station name"
        placeholder="Search station name…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        // text-base (16px) on mobile prevents iOS Safari from auto-zooming the
        // page when the input is focused; text-sm restores the compact size on
        // larger screens.
        className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-base sm:text-sm placeholder-gray-500 focus:outline-none focus:border-gray-500"
      />
      {results.length > 0 && (
        <ul className="absolute z-10 mt-1 w-full max-h-72 overflow-y-auto bg-gray-900 border border-gray-700 rounded-lg shadow-lg">
          {results.map((s) => (
            <li key={s.mapid}>
              <button
                type="button"
                onClick={() => {
                  onSelect(s);
                  setQuery("");
                }}
                className="flex items-center w-full min-h-[44px] text-left px-3 py-2 text-sm hover:bg-gray-800 transition-colors"
              >
                {s.name}
                <span className="ml-2 text-xs text-gray-500">{s.route} Line</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
