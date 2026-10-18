import { clsx } from "clsx";
import { forwardRef, SelectHTMLAttributes, ReactNode } from "react";

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  hint?: string;
  error?: string | null;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { label, hint, error, className, id, children, ...rest },
  ref
) {
  const inputId = id ?? rest.name;
  return (
    <div className="flex flex-col gap-1">
      {label && (
        <label htmlFor={inputId} className="text-sm font-medium text-ink-muted">
          {label}
        </label>
      )}
      <select
        ref={ref}
        id={inputId}
        className={clsx(
          "h-9 rounded border bg-surface-raised px-2 text-base outline-none",
          error ? "border-bad" : "border-line",
          "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
          className
        )}
        aria-invalid={!!error || undefined}
        aria-describedby={hint || error ? `${inputId}-desc` : undefined}
        {...rest}
      >
        {children}
      </select>
      {(hint || error) && (
        <p
          id={`${inputId}-desc`}
          className={clsx("text-xs", error ? "text-bad" : "text-ink-subtle")}
        >
          {error ?? hint}
        </p>
      )}
    </div>
  );
});

export type SelectOption = { value: string; label: ReactNode };