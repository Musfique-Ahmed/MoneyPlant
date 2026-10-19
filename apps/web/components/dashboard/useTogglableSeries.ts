"use client";

import { useState, useCallback, useMemo } from "react";

/**
 * Series-toggle state for Recharts charts. Lets users click a legend item
 * to hide/show the matching series. The state is shared across charts via
 * the optional ``controlled`` / ``onChange`` props.
 */
export function useTogglableSeries() {
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const isVisible = useCallback((name: string) => !hidden.has(name), [hidden]);
  const toggle = useCallback(
    (name: string) => {
      setHidden((prev) => {
        const next = new Set(prev);
        if (next.has(name)) next.delete(name);
        else next.add(name);
        return next;
      });
    },
    [],
  );
  return useMemo(
    () => ({ hidden, setHidden, isVisible, toggle }),
    [hidden, isVisible, toggle],
  );
}
