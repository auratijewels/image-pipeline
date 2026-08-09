import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'
import { SLOTS } from './AngleSlots.jsx'
import { Button, ErrorNote, Panel } from './ui.jsx'

/**
 * Cut-out preview (§4 step A).
 *
 * Previews sit on a checkerboard because a transparent PNG shown on a flat
 * background is indistinguishable from an opaque one — the alpha channel is
 * the entire point of this stage and has to be visible to be judged.
 */
export default function CutoutPanel({ product }) {
  const [available, setAvailable] = useState({})
  const [stats, setStats] = useState({})
  const [errors, setErrors] = useState({})
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [stamp, setStamp] = useState(0)

  const uploaded = SLOTS.filter((s) => product?.angles?.[s.angle])

  useEffect(() => {
    if (!product?.id) return
    api.listCutouts(product.id).then(setAvailable).catch(() => {})
  }, [product?.id])

  async function run(force) {
    setBusy(true)
    setError(null)
    try {
      const res = await api.buildCutouts(product.id, { force })
      setStats(res.cutouts)
      setErrors(res.errors)
      setAvailable(await api.listCutouts(product.id))
      setStamp(Date.now())
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  if (!product?.id || uploaded.length === 0) return null

  const anyBuilt = Object.values(available).some(Boolean)

  return (
    <Panel
      title="Cut-outs"
      action={
        <div className="flex gap-2">
          <Button onClick={() => run(false)} disabled={busy}>
            {busy ? 'Working…' : anyBuilt ? 'Update' : 'Remove backgrounds'}
          </Button>
          {anyBuilt && (
            <Button variant="ghost" onClick={() => run(true)} disabled={busy}>
              Re-run all
            </Button>
          )}
        </div>
      }
    >
      <p className="mb-4 text-xs text-platinum-dim">
        Transparent PNGs cut from each uploaded angle. Judge them on chains and prong gaps, not
        the solid body — that is where mattes fail.
        {busy && ' First run downloads the BiRefNet model (~970 MB) and takes several minutes.'}
      </p>

      <ErrorNote>{error}</ErrorNote>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {uploaded.map(({ angle, label }) => {
          const has = available[angle]
          const stat = stats[angle]
          const failed = errors[angle]
          return (
            <div key={angle}>
              <div
                className="flex aspect-square items-center justify-center overflow-hidden rounded border border-navy-soft/60"
                style={
                  has
                    ? {
                        backgroundImage:
                          'linear-gradient(45deg,#2a3247 25%,transparent 25%),linear-gradient(-45deg,#2a3247 25%,transparent 25%),linear-gradient(45deg,transparent 75%,#2a3247 75%),linear-gradient(-45deg,transparent 75%,#2a3247 75%)',
                        backgroundSize: '16px 16px',
                        backgroundPosition: '0 0,0 8px,8px -8px,-8px 0px',
                        backgroundColor: '#1b2133',
                      }
                    : undefined
                }
              >
                {has ? (
                  <img
                    src={api.cutoutImageUrl(product.id, angle, stamp)}
                    alt={`${label} cut-out`}
                    className="size-full object-contain"
                  />
                ) : (
                  <span className="px-2 text-center text-xs text-platinum-dim">
                    {failed ? 'Failed' : 'Not cut out yet'}
                  </span>
                )}
              </div>

              <p className="mt-1.5 text-sm text-platinum">{label}</p>
              {stat && (
                <p
                  className={`text-xs ${stat.plausible ? 'text-platinum-dim' : 'text-amber-300'}`}
                >
                  {Math.round(stat.coverage * 100)}% kept
                  {stat.cached && ' · cached'}
                  {!stat.plausible && ' · check source'}
                </p>
              )}
              {failed && <p className="mt-0.5 text-xs text-red-300">{failed}</p>}
            </div>
          )
        })}
      </div>
    </Panel>
  )
}
