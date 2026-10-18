"use client";

import { clsx } from "clsx";
import { forwardRef, ButtonHTMLAttributes } from "react";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  iconLeft?: React.ReactNode;
  iconRight?: React.ReactNode;
}

const variantStyles: Record<ButtonVariant, string> = {
  primary:
    "bg-accent text-ink-inverse hover:bg-accent-hover active:bg-accent-hover disabled:opacity-50",
  secondary:
    "bg-surface-raised text-ink border border-line hover:bg-surface-sunken disabled:opacity-50",
  ghost: "bg-transparent text-ink hover:bg-surface-sunken disabled:opacity-50",
  danger: "bg-bad text-ink-inverse hover:opacity-90 disabled:opacity-50",
};

const sizeStyles: Record<ButtonSize, string> = {
  sm: "h-7 px-2.5 text-sm gap-1.5",
  md: "h-9 px-3.5 text-base gap-2",
  lg: "h-11 px-5 text-md gap-2",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = "primary",
    size = "md",
    loading = false,
    iconLeft,
    iconRight,
    className,
    children,
    disabled,
    type = "button",
    ...rest
  },
  ref
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      className={clsx(
        "inline-flex items-center justify-center rounded font-medium",
        "transition-colors duration-150",
        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
        "disabled:cursor-not-allowed",
        variantStyles[variant],
        sizeStyles[size],
        className
      )}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? (
        <span
          aria-hidden
          className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent"
        />
      ) : (
        iconLeft
      )}
      {children}
      {!loading && iconRight}
    </button>
  );
});
