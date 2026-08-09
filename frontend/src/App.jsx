import { useEffect, useState } from 'react'
import { api } from './lib/api.js'

function Panel({ title, children }) {
  return (
    <section className="rounded-lg border border-navy-soft/60 bg-navy/30 p-6">
      <h2 className="mb-4 font-display text-2xl font-light tracking-wide text-platinum">{title}</h2>
      {children}
    </section>
  )
}

function StatusDot({ ok }) {
  return (
    <span
      className={`inline-block size-2 rounded-full ${ok ? 'bg-emerald-400' : 'bg-amber-400'}`}
      aria-hidden
    />
  )
}

export default function App() {
  const [health, setHealth] = useState(null)
  const [assetTypes, setAssetTypes] = useState([])
  const [formats, setFormats] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    Promise.all([api.health(), api.assetTypes(), api.formats()])
      .then(([h, a, f]) => {
        setHealth(h)
        setAssetTypes(a)
        setFormats(f)
      })
      .catch((e) => setError(e.message))
  }, [])

  return (
    <div className="min-h-screen px-8 py-12">
      <header className="mx-auto mb-12 max-w-5xl">
        <h1 className="font-display text-5xl font-light tracking-[0.2em] text-platinum">AURATI</h1>
        <p className="mt-2 text-sm tracking-[0.3em] text-platinum-dim uppercase">Studio</p>
        <p className="mt-4 font-display text-xl text-platinum-dim italic">
          Wear Confidence Everyday
        </p>
      </header>

      <main className="mx-auto grid max-w-5xl gap-6">
        {error && (
          <div className="rounded-lg border border-red-500/40 bg-red-950/40 p-6 text-sm">
            <p className="mb-2 font-medium text-red-300">Backend unreachable</p>
            <p className="text-platinum-dim">{error}</p>
            <p className="mt-3 text-platinum-dim">
              Start it with <code className="text-platinum">.\run.ps1</code> from the repo root.
            </p>
          </div>
        )}

        {health && (
          <Panel title="Status">
            <dl className="grid grid-cols-2 gap-x-8 gap-y-3 text-sm sm:grid-cols-4">
              <div>
                <dt className="text-platinum-dim">Provider</dt>
                <dd className="mt-1 flex items-center gap-2">
                  <StatusDot ok={!health.dry_run} />
                  {health.provider}
                </dd>
              </div>
              <div>
                <dt className="text-platinum-dim">Model</dt>
                <dd className="mt-1 font-mono text-xs">{health.model}</dd>
              </div>
              <div>
                <dt className="text-platinum-dim">Mode</dt>
                <dd className="mt-1">{health.dry_run ? 'Dry run (no spend)' : 'Live'}</dd>
              </div>
              <div>
                <dt className="text-platinum-dim">Budget cap</dt>
                <dd className="mt-1">₹{health.budget_cap_inr} / product</dd>
              </div>
            </dl>
          </Panel>
        )}

        {assetTypes.length > 0 && (
          <Panel title={`Asset types (${assetTypes.length})`}>
            <ul className="grid gap-2 text-sm">
              {assetTypes.map((a) => (
                <li key={a.key} className="flex items-baseline justify-between gap-4 border-b border-navy-soft/30 pb-2">
                  <span>{a.label}</span>
                  <span className="shrink-0 text-xs text-platinum-dim">
                    {a.native_ratio} · {a.pipeline}
                  </span>
                </li>
              ))}
            </ul>
          </Panel>
        )}

        {formats.length > 0 && (
          <Panel title={`Export formats (${formats.length})`}>
            <ul className="grid gap-2 text-sm sm:grid-cols-2">
              {formats.map((f) => (
                <li key={f.key} className="flex items-baseline justify-between gap-4 border-b border-navy-soft/30 pb-2">
                  <span>{f.purpose}</span>
                  <span className="shrink-0 font-mono text-xs text-platinum-dim">
                    {f.width}×{f.height}
                  </span>
                </li>
              ))}
            </ul>
          </Panel>
        )}
      </main>

      <footer className="mx-auto mt-12 max-w-5xl text-xs text-platinum-dim">
        Milestone 1 — scaffold. Product upload lands in Milestone 2.
      </footer>
    </div>
  )
}
