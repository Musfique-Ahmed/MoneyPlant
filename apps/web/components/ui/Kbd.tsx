import { clsx } from "clsx";
import { ReactNode } from "react";

export function Kbd({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <kbd
      className={clsx(
        "inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded border border-line bg-surface-sunken px-1 font-mono text-2xs text-ink-muted",
        className
      )}
    >
      {children}
    </kbd>
  );
}
