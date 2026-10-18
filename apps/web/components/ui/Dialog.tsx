"use client";

import { clsx } from "clsx";
import { ReactNode, useEffect, useRef } from "react";
import { X } from "lucide-react";

export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  size = "md",
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  size?: "sm" | "md" | "lg";
}) {
  const ref = useRef<HTMLDialogElement | null>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const handler = () => onClose();
    el.addEventListener("close", handler);
    return () => el.removeEventListener("close", handler);
  }, [onClose]);

  const sizeClass =
    size === "sm" ? "max-w-sm" : size === "lg" ? "max-w-2xl" : "max-w-md";

  return (
    <dialog
      ref={ref}
      className={clsx(
        "w-full rounded-md border border-line bg-surface-raised p-0 shadow-elev2",
        sizeClass
      )}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
    >
      <div className="flex items-start justify-between gap-3 border-b border-line px-4 py-3">
        <div>
          <div className="text-md font-semibold text-ink">{title}</div>
          {description && <div className="text-sm text-ink-muted">{description}</div>}
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close dialog"
          className="rounded p-1 text-ink-muted hover:bg-surface-sunken hover:text-ink"
        >
          <X size={16} />
        </button>
      </div>
      <div className="p-4">{children}</div>
      {footer && <div className="border-t border-line bg-surface-sunken px-4 py-3">{footer}</div>}
    </dialog>
  );
}
