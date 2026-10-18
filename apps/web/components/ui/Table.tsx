import { clsx } from "clsx";
import { ReactNode } from "react";

export function Table({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={clsx("overflow-hidden rounded-md border border-line bg-surface-raised", className)}>
      <table className="w-full text-sm tabular-nums" data-tabular>
        {children}
      </table>
    </div>
  );
}

export function THead({ children }: { children: ReactNode }) {
  return <thead className="bg-surface-sunken text-left text-xs uppercase tracking-wide text-ink-muted">{children}</thead>;
}

export function TBody({ children }: { children: ReactNode }) {
  return <tbody className="divide-y divide-line">{children}</tbody>;
}

export function TR({ children, onClick, selected }: { children: ReactNode; onClick?: () => void; selected?: boolean }) {
  return (
    <tr
      onClick={onClick}
      className={clsx(
        onClick && "cursor-pointer hover:bg-surface-sunken",
        selected && "bg-accent-soft"
      )}
    >
      {children}
    </tr>
  );
}

export function TH({ children, align = "left", className }: { children: ReactNode; align?: "left" | "right" | "center"; className?: string }) {
  return (
    <th
      className={clsx(
        "px-3 py-2 font-medium",
        align === "right" && "text-right",
        align === "center" && "text-center",
        className
      )}
    >
      {children}
    </th>
  );
}

export function TD({ children, align = "left", className }: { children: ReactNode; align?: "left" | "right" | "center"; className?: string }) {
  return (
    <td
      className={clsx(
        "px-3 py-2",
        align === "right" && "text-right",
        align === "center" && "text-center",
        className
      )}
    >
      {children}
    </td>
  );
}
