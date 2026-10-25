import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const styles: Record<Variant, string> = {
  primary:
    "bg-indigo-500 text-white hover:bg-indigo-400 active:bg-indigo-600 active:text-white",
  secondary:
    "border border-slate-700 bg-slate-800 text-slate-100 hover:bg-slate-700 hover:border-slate-600 active:bg-slate-900",
  ghost:
    "bg-transparent text-slate-300 hover:bg-slate-800 hover:text-slate-100 active:bg-slate-900",
  danger:
    "border border-rose-900/60 bg-rose-950/40 text-rose-200 hover:border-rose-800 hover:bg-rose-900/60 active:bg-rose-900",
};

export function Button({
  variant = "primary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-400 disabled:pointer-events-none disabled:opacity-50 ${styles[variant]} ${className}`}
      {...props}
    />
  );
}
