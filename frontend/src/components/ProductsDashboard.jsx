import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'
import { Button, ErrorNote, Panel, StatusChip } from './ui.jsx'

export default function ProductsDashboard({ onNew, onOpen }) {
  const [products, setProducts] = useState(null)
  const [error, setError] = useState(null)

  const load = () =>
    api
      .listProducts()
      .then(setProducts)
      .catch((e) => setError(e.message))

  useEffect(() => {
    load()
  }, [])

  async function remove(product) {
    if (!confirm(`Delete ${product.code} — ${product.name}? Uploads are removed too.`)) return
    try {
      await api.deleteProduct(product.id)
      load()
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <Panel title="Products" action={<Button onClick={onNew}>New product</Button>}>
      <ErrorNote>{error}</ErrorNote>

      {products === null && !error && <p className="text-sm text-platinum-dim">Loading…</p>}

      {products?.length === 0 && (
        <div className="rounded border border-dashed border-navy-soft/70 px-6 py-12 text-center">
          <p className="font-display text-xl text-platinum">No products yet</p>
          <p className="mt-2 text-sm text-platinum-dim">
            Add one with its real-world dimensions and up to five angles.
          </p>
          <Button className="mt-5" onClick={onNew}>
            New product
          </Button>
        </div>
      )}

      {products?.length > 0 && (
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {products.map((p) => (
            <li
              key={p.id}
              className="group overflow-hidden rounded border border-navy-soft/60 bg-midnight/40"
            >
              <button
                type="button"
                onClick={() => onOpen(p.id)}
                className="block w-full text-left"
              >
                <div className="flex aspect-4/3 items-center justify-center bg-midnight/70">
                  {p.angles?.front ? (
                    <img
                      src={api.angleImageUrl(p.id, 'front', p.angles.front.uploaded_at)}
                      alt={`${p.name} front angle`}
                      className="size-full object-cover"
                    />
                  ) : (
                    <span className="text-xs text-platinum-dim">No front image</span>
                  )}
                </div>

                <div className="p-4">
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="font-mono text-xs text-platinum-dim">{p.code}</span>
                    <StatusChip status={p.status} />
                  </div>
                  <p className="mt-1 font-display text-lg text-platinum">{p.name}</p>
                  <p className="mt-1 text-xs text-platinum-dim capitalize">
                    {p.category}
                    {p.primary_mm ? ` · ${p.primary_mm} mm` : ''}
                  </p>
                  {p.blockers?.length > 0 && (
                    <p className="mt-2 text-xs text-amber-300/80">
                      {p.blockers.length} item{p.blockers.length > 1 ? 's' : ''} outstanding
                    </p>
                  )}
                </div>
              </button>

              <div className="flex justify-end border-t border-navy-soft/40 px-3 py-2">
                <button
                  type="button"
                  onClick={() => remove(p)}
                  className="text-xs text-platinum-dim transition-colors hover:text-red-300"
                >
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  )
}
