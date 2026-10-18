import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Monaco",
          "Consolas",
          "monospace",
        ],
      },
      colors: {
        // Operate-mode Restrained palette + one Committed accent.
        surface: {
          DEFAULT: "rgb(var(--color-surface) / <alpha-value>)",
          sunken: "rgb(var(--color-surface-sunken) / <alpha-value>)",
          raised: "rgb(var(--color-surface-raised) / <alpha-value>)",
        },
        ink: {
          DEFAULT: "rgb(var(--color-ink) / <alpha-value>)",
          muted: "rgb(var(--color-ink-muted) / <alpha-value>)",
          subtle: "rgb(var(--color-ink-subtle) / <alpha-value>)",
          inverse: "rgb(var(--color-ink-inverse) / <alpha-value>)",
        },
        line: "rgb(var(--color-line) / <alpha-value>)",
        accent: {
          DEFAULT: "rgb(var(--color-accent) / <alpha-value>)",
          hover: "rgb(var(--color-accent-hover) / <alpha-value>)",
          soft: "rgb(var(--color-accent-soft) / <alpha-value>)",
        },
        ok: "rgb(var(--color-ok) / <alpha-value>)",
        warn: "rgb(var(--color-warn) / <alpha-value>)",
        bad: "rgb(var(--color-bad) / <alpha-value>)",
        info: "rgb(var(--color-info) / <alpha-value>)",
      },
      fontSize: {
        // 1.2 ratio, base 14px — disciplined scale.
        "2xs": ["0.6875rem", { lineHeight: "1rem" }], // 11
        xs: ["0.75rem", { lineHeight: "1.1rem" }], // 12
        sm: ["0.8125rem", { lineHeight: "1.2rem" }], // 13
        base: ["0.875rem", { lineHeight: "1.4rem" }], // 14
        md: ["1rem", { lineHeight: "1.5rem" }], // 16
        lg: ["1.125rem", { lineHeight: "1.6rem" }], // 18
        xl: ["1.375rem", { lineHeight: "1.8rem" }], // 22
        "2xl": ["1.625rem", { lineHeight: "2rem" }], // 26
        "3xl": ["1.875rem", { lineHeight: "2.2rem" }], // 30
      },
      borderRadius: {
        xs: "0.125rem",
        sm: "0.25rem",
        DEFAULT: "0.375rem",
        md: "0.5rem",
        lg: "0.75rem",
        xl: "1rem",
      },
      boxShadow: {
        // Disciplined, one elevation.
        elev1: "0 1px 0 0 rgb(var(--color-line) / 1), 0 1px 2px 0 rgb(0 0 0 / 0.04)",
        elev2: "0 1px 0 0 rgb(var(--color-line) / 1), 0 4px 12px -4px rgb(0 0 0 / 0.10)",
      },
      transitionDuration: {
        DEFAULT: "150ms",
      },
    },
  },
  plugins: [],
};

export default config;
