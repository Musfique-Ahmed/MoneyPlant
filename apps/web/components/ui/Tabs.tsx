"use client";

import { clsx } from "clsx";
import { ReactNode, useState } from "react";

export interface TabItem {
  id: string;
  label: ReactNode;
  content: ReactNode;
  disabled?: boolean;
}

export function Tabs({
  items,
  defaultId,
  ariaLabel,
}: {
  items: TabItem[];
  defaultId?: string;
  ariaLabel: string;
}) {
  const [active, setActive] = useState(defaultId ?? items[0]?.id);
  const current = items.find((i) => i.id === active);
  return (
    <div>
      <div role="tablist" aria-label={ariaLabel} className="flex border-b border-line">
        {items.map((item) => {
          const isActive = item.id === active;
          return (
            <button
              key={item.id}
              role="tab"
              aria-selected={isActive}
              aria-controls={`tab-${item.id}`}
              id={`tab-${item.id}-button`}
              type="button"
              disabled={item.disabled}
              onClick={() => setActive(item.id)}
              className={clsx(
                "px-3 py-2 text-sm font-medium",
                "border-b-2 -mb-px",
                isActive ? "border-accent text-ink" : "border-transparent text-ink-muted hover:text-ink",
                item.disabled && "cursor-not-allowed opacity-50"
              )}
            >
              {item.label}
            </button>
          );
        })}
      </div>
      {current && (
        <div role="tabpanel" id={`tab-${current.id}`} aria-labelledby={`tab-${current.id}-button`} className="py-3">
          {current.content}
        </div>
      )}
    </div>
  );
}
