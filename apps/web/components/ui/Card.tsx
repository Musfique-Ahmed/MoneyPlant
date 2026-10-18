import { clsx } from "clsx";
import { ReactNode } from "react";

export function Card({
  children,
  className,
  as: As = "div",
}: {
  children: ReactNode;
  className?: string;
  as?: "div" | "section" | "article";
}) {
  return (
    <As
      className={clsx(
        "rounded-md border border-line bg-surface-raised shadow-elev1",
        className
      )}
    >
      {children}
    </As>
  );
}

export function CardHeader({
  title,
  description,
  actions,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-line px-4 py-3">
      <div className="min-w-0">
        <div className="text-md font-semibold text-ink">{title}</div>
        {description && <div className="text-sm text-ink-muted">{description}</div>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}

export function CardBody({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={clsx("p-4", className)}>{children}</div>;
}

export function CardFooter({ children }: { children: ReactNode }) {
  return <div className="border-t border-line bg-surface-sunken px-4 py-2 text-xs text-ink-subtle">{children}</div>;
}