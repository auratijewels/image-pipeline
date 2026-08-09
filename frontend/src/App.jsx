import { useEffect, useState } from 'react'
import ProductEditor from './components/ProductEditor.jsx'
import ProductsDashboard from './components/ProductsDashboard.jsx'
import { ErrorNote } from './components/ui.jsx'
import { api } from './lib/api.js'

export default function App() {
  const [view, setView] = useState({ name: 'list' })
  const [health, setHealth] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.health().then(setHealth).catch((e) => setError(e.message))
  }, [])

  return (
    <div className="min-h-screen px-6 py-10 sm:px-8">
      <header className="mx-auto mb-10 flex max-w-6xl flex-wrap items-end justify-between gap-6">
        <div>
          <h1 className="font-display text-4xl font-light tracking-[0.2em] text-platinum">
            AURATI
          </h1>
          <p className="mt-1 text-xs tracking-[0.3em] text-platinum-dim uppercase">Studio</p>
        </div>
        {health && (
          <dl className="flex flex-wrap gap-x-8 gap-y-2 text-xs">
            <div>
              <dt className="text-platinum-dim">Provider</dt>
              <dd className="mt-0.5 flex items-center gap-1.5 text-platinum">
                <span
                  className={`inline-block size-1.5 rounded-full ${
                    health.dry_run ? 'bg-amber-400' : 'bg-emerald-400'
                  }`}
                />
                {health.dry_run ? 'Dry run — no spend' : health.model}
              </dd>
            </div>
            <div>
              <dt className="text-platinum-dim">Budget cap</dt>
              <dd className="mt-0.5 text-platinum">₹{health.budget_cap_inr} / product</dd>
            </div>
          </dl>
        )}
      </header>

      <main className="mx-auto grid max-w-6xl gap-6">
        {error && (
          <ErrorNote>
            Backend unreachable — {error}. Start it with <code>.\run.ps1</code>.
          </ErrorNote>
        )}

        {view.name === 'list' && (
          <ProductsDashboard
            onNew={() => setView({ name: 'edit', id: null })}
            onOpen={(id) => setView({ name: 'edit', id })}
          />
        )}

        {view.name === 'edit' && (
          <ProductEditor
            key={view.id ?? 'new'}
            productId={view.id}
            onDone={(id) => setView({ name: 'edit', id })}
            onCancel={() => setView({ name: 'list' })}
          />
        )}
      </main>

      <footer className="mx-auto mt-12 max-w-6xl text-xs text-platinum-dim">
        Milestone 2 — products and uploads. Cut-out and the scale pipeline are next.
      </footer>
    </div>
  )
}
