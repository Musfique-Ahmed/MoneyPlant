import { clsx } from "clsx";
import { forwardRef, InputHTMLAttributes, ReactNode } from "react";

interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "prefix"> {
  label?: string;
  hint?: string;
  error?: string | null;
  prefix?: ReactNode;
  suffix?: ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, hint, error, prefix, suffix, className, id, ...rest },
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
      <div
        className={clsx(
          "flex h-9 items-stretch overflow-hidden rounded border bg-surface-raised",
          error ? "border-bad" : "border-line",
          "focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-accent"
        )}
      >
        {prefix && (
          <span className="flex items-center px-2 text-sm text-ink-subtle">{prefix}</span>
        )}
        <input
          ref={ref}
          id={inputId}
          className={clsx("min-w-0 flex-1 bg-transparent px-2 text-base outline-none", className)}
          aria-invalid={!!error || undefined}
          aria-describedby={hint || error ? `${inputId}-desc` : undefined}
          {...rest}
        />
        {suffix && (
          <span className="flex items-center px-2 text-sm text-ink-subtle">{suffix}</span>
        )}
      </div>
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
