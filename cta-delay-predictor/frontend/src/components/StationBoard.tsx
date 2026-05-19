"use client";

import { useEffect, useState } from "react";
import type { ArrivalItem, StationArrivalsResponse } from "@/lib/types";
import TrainStatusChip from "./TrainStatusChip";

function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
}

function ArrivalRow({ arrival }: { arrival: ArrivalItem }) {
  const routeColor =
    arrival.route?.toLowerCase() === "red" ? "text-[#c60c30]" : "text-[#00a1de]";

  return (
    <tr className="border-b border-gray-800 hover:bg-gray-900 transition-colors">
      <td className="py-3 px-3">
        <span className={`font-semibold text-sm ${routeColor}`}>
          {arrival.route}
        </span>
      </td>
      <td className="py-3 px-3 text-sm">
        <div className="font-medium">{arrival.destination || "—"}</div>
        <div className="text-gray-500 text-xs">Run {arrival.run_number}</div>
      </td>
      <td className="py-3 px-3 text-sm text-gray-300">
        {arrival.is_approaching ? (
          <span className="text-yellow-400 font-semibold animate-pulse">Due</span>
        ) : arrival.cta_eta_minutes !== null ? (
          `${arrival.cta_eta_minutes.toFixed(0)} min`
        ) : (
          fmtTime(arrival.cta_eta)
        )}
      </td>
      <td className="py-3 px-3 text-sm text-gray-300">
        {fmtTime(arrival.scheduled_time)}
      </td>
      <td className="py-3 px-3">
        <TrainStatusChip
          status={arrival.delay_status}
          delayMinutes={arrival.model_delay_minutes}
        />
      </td>
      <td className="py-3 px-3 text-xs text-gray-500 hidden sm:table-cell">
        {arrival.p10_minutes !== null && arrival.p90_minutes !== null
          ? `${arrival.p10_minutes > 0 ? "+" : ""}${arrival.p10_minutes.toFixed(1)} / ${arrival.p90_minutes > 0 ? "+" : ""}${arrival.p90_minutes.toFixed(1)} m`
          : "—"}
      </td>
    </tr>
  );
}

interface Props {
  data: StationArrivalsResponse;
}

export default function StationBoard({ data }: Props) {
  const routeColor =
    data.route?.toLowerCase() === "red"
      ? "border-[#c60c30]"
      : "border-[#00a1de]";

  const asOf = new Date(data.as_of).toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    hour12: true,
  });

  return (
    <div className="space-y-4">
      <div className={`border-l-4 pl-3 ${routeColor}`}>
        <h2 className="text-xl font-bold">{data.station_name}</h2>
        <p className="text-gray-400 text-xs">As of {asOf}</p>
      </div>

      {data.arrivals.length === 0 ? (
        <p className="text-gray-500">No upcoming arrivals.</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-800">
          <table className="w-full text-left">
            <thead>
              <tr className="text-xs text-gray-400 bg-gray-900 border-b border-gray-800">
                <th className="py-2 px-3">Line</th>
                <th className="py-2 px-3">Destination</th>
                <th className="py-2 px-3">CTA ETA</th>
                <th className="py-2 px-3">Scheduled</th>
                <th className="py-2 px-3">Status</th>
                <th className="py-2 px-3 hidden sm:table-cell">
                  p10 / p90 delay
                </th>
              </tr>
            </thead>
            <tbody>
              {data.arrivals.map((a) => (
                <ArrivalRow key={`${a.run_number}-${a.cta_eta}`} arrival={a} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-xs text-gray-600">
        Model status shown when trained. &quot;—&quot; means no model loaded yet
        — collect data and run{" "}
        <code className="bg-gray-900 px-1 rounded">
          python -m backend.ml.train
        </code>
        .
      </p>
    </div>
  );
}
