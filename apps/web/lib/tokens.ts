/**
 * Design tokens. The single typed mirror of `app/globals.css`.
 * Components should import values from here, not hard-code RGB or hex.
 */

export const color = {
  surface: "rgb(var(--color-surface))",
  surfaceSunken: "rgb(var(--color-surface-sunken))",
  surfaceRaised: "rgb(var(--color-surface-raised))",
  ink: "rgb(var(--color-ink))",
  inkMuted: "rgb(var(--color-ink-muted))",
  inkSubtle: "rgb(var(--color-ink-subtle))",
  line: "rgb(var(--color-line))",
  accent: "rgb(var(--color-accent))",
  accentHover: "rgb(var(--color-accent-hover))",
  accentSoft: "rgb(var(--color-accent-soft))",
  ok: "rgb(var(--color-ok))",
  warn: "rgb(var(--color-warn))",
  bad: "rgb(var(--color-bad))",
  info: "rgb(var(--color-info))",
} as const;

export const radii = {
  xs: "0.125rem",
  sm: "0.25rem",
  md: "0.375rem",
  lg: "0.5rem",
  xl: "0.75rem",
} as const;

export const elevation = {
  elev1: "0 1px 0 0 rgb(var(--color-line) / 1), 0 1px 2px 0 rgb(0 0 0 / 0.04)",
  elev2: "0 1px 0 0 rgb(var(--color-line) / 1), 0 4px 12px -4px rgb(0 0 0 / 0.10)",
} as const;

export const motion = {
  fast: "120ms",
  base: "150ms",
  slow: "240ms",
} as const;

export type ColorToken = keyof typeof color;
