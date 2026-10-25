import type { ReactNode } from "react";

export type BadgeTone = "neutral" | "info" | "success" | "warning" | "danger";

const toneStyles: Record<BadgeTone, string> = {
  neutral: "bg-slate-500/15 text-slate-300",
  info: "bg-sky-500/15 text-sky-300",
  success: "bg-emerald-500/15 text-emerald-300",
  warning: "bg-amber-500/15 text-amber-300",
  danger: "bg-rose-500/15 text-rose-300",
};

/** Small status pill used for sync states, urgency tiers and risk labels. */
export function StatusBadge({
  tone = "neutral",
  className = "",
  children,
}: {
  tone?: BadgeTone;
  className?: string;
  children: ReactNode;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${toneStyles[tone]} ${className}`}
    >
      {children}
    </span>
  );
}
