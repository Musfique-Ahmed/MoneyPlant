import Link from "next/link";
import { ArrowRight, BarChart3, ShieldCheck, FileSpreadsheet, Sparkles } from "lucide-react";

export default function Landing() {
  return (
    <main className="min-h-screen bg-surface">
      <div className="mx-auto max-w-5xl px-6 py-16">
        <header className="flex items-center justify-between">
          <div className="text-md font-semibold tracking-tight">MoneyPlant</div>
          <Link
            href="/dashboard"
            className="inline-flex h-9 items-center gap-1.5 rounded bg-accent px-3.5 text-base font-medium text-ink-inverse hover:bg-accent-hover"
          >
            Open dashboard <ArrowRight size={16} />
          </Link>
        </header>

        <section className="mt-16">
          <h1 className="max-w-3xl text-3xl font-semibold leading-tight tracking-tight text-ink">
            A finance copilot for small businesses.
          </h1>
          <p className="mt-4 max-w-2xl text-lg text-ink-muted">
            Import your transactions, model scenarios deterministically, get rule-based
            decision support, and ask questions in plain language — all with privacy controls
            you can read.
          </p>
          <div className="mt-6 flex gap-3">
            <Link
              href="/dashboard"
              className="inline-flex h-11 items-center gap-2 rounded bg-accent px-5 text-md font-medium text-ink-inverse hover:bg-accent-hover"
            >
              Open dashboard <ArrowRight size={18} />
            </Link>
            <Link
              href="/data"
              className="inline-flex h-11 items-center gap-2 rounded border border-line bg-surface-raised px-5 text-md font-medium text-ink hover:bg-surface-sunken"
            >
              Import data
            </Link>
          </div>
        </section>

        <section className="mt-16 grid grid-cols-1 gap-4 md:grid-cols-2">
          <Pillar icon={<FileSpreadsheet size={18} />} title="Safe ingestion">
            CSV and XLSX previews with auto-suggested column mapping. We read values, never
            evaluate workbook formulas.
          </Pillar>
          <Pillar icon={<BarChart3 size={18} />} title="Deterministic engine">
            Monthly cash, profit, inventory, and unit economics computed server-side. The
            frontend never does authoritative math.
          </Pillar>
          <Pillar icon={<ShieldCheck size={18} />} title="Rules, not vibes">
            Hard business constraints are checked first. Laya and the LLM cannot override
            them — the recommendation is the rules&apos; verdict.
          </Pillar>
          <Pillar icon={<Sparkles size={18} />} title="Private by default">
            Local Ollama, or your own OpenAI / Anthropic key. No data is sent to a third party
            without an explicit mode change in the UI.
          </Pillar>
        </section>
      </div>
    </main>
  );
}

function Pillar({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-md border border-line bg-surface-raised p-4">
      <div className="mb-2 flex items-center gap-2 text-ink-muted">{icon}<span className="text-sm font-medium uppercase tracking-wide">{title}</span></div>
      <p className="text-base text-ink">{children}</p>
    </div>
  );
}
