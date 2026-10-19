"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";

/**
 * Three-way theme switch for the top bar.
 *
 * Cycles light → dark → system → light. The actual class on <html> is
 * managed by next-themes; this component just sets the choice. The
 * `mounted` guard avoids a hydration mismatch (the server can't know
 * the user's stored theme).
 */
export function ThemeToggle() {
  const { theme, setTheme, resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  if (!mounted) {
    // Reserve the same footprint so the top bar doesn't jump on hydration.
    return <span className="h-7 w-7" aria-hidden />;
  }

  // Use the *resolved* theme to pick the icon, so "System" reflects whatever
  // is actually being shown right now.
  const isDark = resolvedTheme === "dark";
  const next: "dark" | "system" | "light" = isDark ? "light" : "dark";

  return (
    <Button
      size="sm"
      variant="ghost"
      onClick={() => setTheme(next)}
      aria-label={`Theme: ${theme ?? "system"}. Click to switch to ${next}.`}
      title={`Theme: ${theme ?? "system"} → ${next}`}
    >
      {theme === "system" ? (
        <Monitor size={14} aria-hidden />
      ) : isDark ? (
        <Moon size={14} aria-hidden />
      ) : (
        <Sun size={14} aria-hidden />
      )}
    </Button>
  );
}
