import { clsx } from "clsx";
import { ReactNode } from "react";

export function EmptyState({
  title,
  description,
  action,
  icon,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-md border border-dashed border-line bg-surface-sunken p-8 text-center">
      {icon && <div className="text-ink-subtle">{icon}</div>}
      <div className="text-md font-semibold text-ink">{title}</div>
      {description && (
        <p className="max-w-md text-sm text-ink-muted">{description}</p>
      )}
      {action}
    </div>
  );
}

export function ErrorState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-md border border-bad/30 bg-bad/5 p-8 text-center">
      <div className="text-md font-semibold text-bad">{title}</div>
      {description && <p className="max-w-md text-sm text-ink-muted">{description}</p>}
      {action}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      aria-hidden
      className={clsx("animate-pulse rounded bg-surface-sunken", className)}
    />
  );
}
