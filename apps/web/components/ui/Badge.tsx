import { clsx } from "clsx";
import { ReactNode } from "react";

type Tone = "neutral" | "ok" | "warn" | "bad" | "info" | "accent";

const toneStyles: Record<Tone, string> = {
  neutral: "bg-surface-sunken text-ink-muted border-line",
  ok: "bg-ok/10 text-ok border-ok/30",
  warn: "bg-warn/10 text-warn border-warn/30",
  bad: "bg-bad/10 text-bad border-bad/30",
  info: "bg-info/10 text-info border-info/30",
  accent: "bg-accent-soft text-accent border-accent/30",
};

export function Badge({
  tone = "neutral",
  children,
  className,
}: {
  tone?: Tone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded-sm border px-1.5 py-0.5 text-xs font-medium",
        toneStyles[tone],
        className
      )}
    >
      {children}
    </span>
  );
}
