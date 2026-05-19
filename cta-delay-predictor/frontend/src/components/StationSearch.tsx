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
        placeholder="Search station name…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm placeholder-gray-500 focus:outline-none focus:border-gray-500"
      />
      {results.length > 0 && (
        <ul className="absolute z-10 mt-1 w-full bg-gray-900 border border-gray-700 rounded-lg overflow-hidden shadow-lg">
          {results.map((s) => (
            <li key={s.mapid}>
              <button
                onClick={() => {
                  onSelect(s);
                  setQuery("");
                }}
                className="w-full text-left px-3 py-2 text-sm hover:bg-gray-800 transition-colors"
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
