# Design Decisions — MoneyPlant

This document is the durable visual contract for the MoneyPlant UI. It stands in for `DESIGN.md` (Impeccable's shipped documenter would normally write `DESIGN.md` from the built world; that pass requires bash and is deferred to a follow-up session).

## 1. Mode

**Operate.** The user is in a task — understanding their business, importing records, simulating a decision, reading a report. Earned familiarity is the bar. The interface disappears into the task.

Persuade / Read / Experience surfaces are out of scope for this product.

## 2. World: "Disciplined Ledger"

A Restrained, neutral, two-layer workspace inspired by **working software** — Linear, Tana, the Bloomberg terminal's information density without its visual noise. Not a marketing surface. Not a glassmorphic dashboard. Not a generic template.

The world's material is:

- **Surfaces** — two: a slightly cooler **sidebar surface** (`--surface-sidebar`) and a lighter **content surface** (`--surface-content`). No gradients, no glow, no glass.
- **Borders** — 1 px hairlines, low-contrast. Never a colored `border-left` above 1 px.
- **Type** — one family, **Inter** (system fallback stack). Fixed rem scale, ratio **1.2**. Display never exceeds **2.25 rem** (3 rem maximum on a marketing route, which this product does not have). Body measure **65–75ch**. Tabular numerals on all data.
- **Color strategy** — **Restrained**. One brand accent (`--accent`), used for primary actions, current selection, and a single state indicator. Four semantic states (`success`, `warning`, `danger`, `info`). Two neutral layers for sidebar vs content.
- **Density** — high. Tables with many rows, panels with many labels, dense information when users need it.
- **Motion** — 150–250 ms. Conveys state, never decorates. No orchestrated page-load sequences. No transitions on every section. One authored moment per route, not one identical entrance.
- **Icons** — **lucide-react** (or locally-authored SVG if lucide is rejected in QA). One weight, one stroke. Never Unicode glyphs standing in for icons.
- **Charts** — **Recharts**. Tabular numerals. Accessible table alternative below every chart. Color is never the only differentiator — shape and label always present.

## 3. Tokens (high-level)

CSS custom properties in `apps/web/app/globals.css`, mirrored in `apps/web/lib/tokens.ts`:

```
--font-sans: 'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
--font-numeric: 'Inter', system-ui, sans-serif; /* tabular-nums */

--text-1: 0.6875rem;   /* 11px — eyebrow / metadata */
--text-2: 0.8125rem;   /* 13px — body small */
--text-3: 0.9375rem;   /* 15px — body */
--text-4: 1.125rem;    /* 18px — lead */
--text-5: 1.5rem;      /* 24px — h3 */
--text-6: 1.875rem;    /* 30px — h2 */
--text-7: 2.25rem;     /* 36px — h1 */

--space-1: 0.25rem; --space-2: 0.5rem; --space-3: 0.75rem;
--space-4: 1rem; --space-5: 1.5rem; --space-6: 2rem;
--space-7: 3rem; --space-8: 4rem;

--radius-1: 4px; --radius-2: 6px; --radius-3: 8px;

--shadow-1: 0 1px 2px rgba(15, 23, 42, 0.06), 0 1px 1px rgba(15, 23, 42, 0.04);
--shadow-2: 0 2px 6px rgba(15, 23, 42, 0.08), 0 1px 2px rgba(15, 23, 42, 0.05);

--surface-content: #FAFBFC;       /* warm off-white */
--surface-sidebar: #F2F4F7;       /* cooler neutral */
--surface-elevated: #FFFFFF;
--border-default: #E5E7EB;
--border-strong: #D1D5DB;

--text-primary: #0F172A;
--text-secondary: #475569;
--text-muted: #64748B;
--text-inverse: #FFFFFF;

--accent: #1E5A4E;               /* deep teal — finance-adjacent, calm */
--accent-hover: #174A40;
--accent-pressed: #103A32;
--accent-bg: rgba(30, 90, 78, 0.08);

--success: #15803D;
--warning: #B45309;
--danger: #B91C1C;
--info: #1D4ED8;

--focus-ring: 0 0 0 2px var(--surface-content), 0 0 0 4px var(--accent);

--motion-fast: 120ms;
--motion-base: 180ms;
--motion-slow: 240ms;
--motion-ease: cubic-bezier(0.2, 0.0, 0.0, 1.0);
```

A dark theme is **not** shipped in MVP. The physical use scene is a small-business owner at a desk in daytime light; a light surface earns its presence.

## 4. Component vocabulary

Built locally in `apps/web/components/ui/`:

| Component | Required states |
|---|---|
| `Button` | default, hover, active, focus-visible, disabled, loading |
| `Input` | default, hover, focus-visible, filled, error, disabled |
| `Select` | default, hover, focus-visible, open, disabled |
| `Tabs` | default, hover, selected, focus-visible |
| `Dialog` | uses native `<dialog>`; default, focus trap, escape, scrim |
| `Table` | default, hover row, focus-visible cell, sortable header |
| `Card` | default, hover (when interactive), focus-visible |
| `Badge` | neutral, success, warning, danger, info |
| `Skeleton` | default (single repeating animation) |
| `EmptyState` | title, description, primary action |
| `ErrorState` | title, description, recovery action |
| `Kbd` | default |

Every interactive component ships with all required states. No decorative motion. Modals are used only when interruption is genuinely required; default flows are inline.

## 5. Layout

- **App shell:** sidebar (240 px) + content. Sidebar collapses below 1024 px to a top bar with a slide-down menu. Mobile breakpoint at 640 px.
- **Page header:** title, period selector (where relevant), primary action right-aligned.
- **Dashboard:** no hero metric template. The page is a working summary, not a marketing poster. Metrics in a 12-column grid that adapts.
- **Tables:** first column left-aligned, numeric columns right-aligned with tabular numerals, 32 px row height, alternating row hover.
- **Charts:** in a `Card` with title, action menu, and a hidden `<table>` summary for screen readers.

## 6. Anti-patterns explicitly avoided

The following Impeccable craft-floor bans are enforced:

- No kicker / eyebrow labels above headings.
- No section numbers (`01 / 02 / 03`) unless the sequence itself is data.
- No same-size icon + heading + text cards as the page structure.
- No gradient text.
- No glassmorphism or decorative blur.
- No colored `border-left` above 1 px on cards, callouts, alerts.
- No zero-blur hard offset shadows outside a deliberate neobrutalist world (we did not choose that world).
- No sparklines, progress rings, or soft-shadowed rectangles standing in for content.
- No monospace as a costume for "technical" (tabular numerals are the only place monospace-equivalent applies).
- No Unicode glyphs or emoji as icons.
- No display fonts in product UI labels, buttons, or data.

## 7. What this design is NOT

- It is not a marketing site.
- It is not dark-mode-first.
- It is not gamified.
- It is not a generic admin template.

## 8. Impeccable limitation callout

This document was authored without running `node .claude/skills/impeccable/scripts/concept-seed.mjs` because the bash tool was unavailable in this session. The visual world was selected by the implementer using the Operate-mode craft floor (`reference/operate.md` and `reference/craft-floor.md`), with documented rationale above. To run the formal Impeccable roll:

```
node .claude/skills/impeccable/scripts/context.mjs --target apps/web/app/(app)/dashboard/page.tsx
node .claude/skills/impeccable/scripts/concept-seed.mjs --scope direction --mode operate
```

in a session where bash works. The shipped `impeccable-documenter` will then rewrite this file as `DESIGN.md` from the actual built world.