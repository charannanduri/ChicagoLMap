import type { DelayStatus } from "@/lib/types";

const CONFIG: Record<
  NonNullable<DelayStatus>,
  { label: string; className: string }
> = {
  ahead: {
    label: "Early",
    className: "bg-sky-900 text-sky-300 border-sky-700",
  },
  on_time: {
    label: "On time",
    className: "bg-green-900 text-green-300 border-green-700",
  },
  behind: {
    label: "Late",
    className: "bg-red-900 text-red-300 border-red-700",
  },
};

interface Props {
  status: DelayStatus;
  delayMinutes?: number | null;
}

export default function TrainStatusChip({ status, delayMinutes }: Props) {
  if (!status) {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs border bg-gray-800 text-gray-400 border-gray-700">
        —
      </span>
    );
  }

  const { label, className } = CONFIG[status];
  const suffix =
    delayMinutes !== null && delayMinutes !== undefined
      ? ` ${delayMinutes > 0 ? "+" : ""}${delayMinutes.toFixed(1)}m`
      : "";

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${className}`}
    >
      {label}
      {suffix}
    </span>
  );
}
