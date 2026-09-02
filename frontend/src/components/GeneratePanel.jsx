import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api.js'
import { Button, ErrorNote, Panel, StatusChip } from './ui.jsx'

const LEVEL_STYLE = {
  info: 'text-platinum-dim',
  warn: 'text-amber-300',
  error: 'text-red-300',
  done: 'text-emerald-300',
}

/**
 * Processing view and results gallery.
 *
 * Progress arrives over SSE rather than polling: a run takes tens of seconds
 * and costs money, so the user needs to see which step is running and be able
 * to stop it. The stream replays history on connect, so a refresh mid-run
 * shows the whole log rather than resuming blank.
 */
export default function GeneratePanel({ product, assetTypes }) {
  const [job, setJob] = useState(null)
  const [events, setEvents] = useState([])
  const [available, setAvailable] = useState({})
  const [error, setError] = useState(null)
  const [stamp, setStamp] = useState(0)
  const sourceRef = useRef(null)
  const logRef = useRef(null)

  const running = job && ['queued', 'running'].includes(job.status)

  useEffect(() => {
    if (!product?.id) return
    api.listGeneratedAssets(product.id).then(setAvailable).catch(() => {})
  }, [product?.id])

  // Close the stream on unmount, or the connection leaks for the session.
  useEffect(() => () => sourceRef.current?.close(), [])

  function listen(jobId) {
    sourceRef.current?.close()
    const source = new EventSource(api.jobEventsUrl(jobId))
    sourceRef.current = source

    source.onmessage = (e) => {
      const event = JSON.parse(e.data)
      setEvents((prev) => [...prev, event])
      queueMicrotask(() => {
        if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
      })
    }
    source.addEventListener('end', async (e) => {
      source.close()
      setJob(JSON.parse(e.data))
      setAvailable(await api.listGeneratedAssets(product.id).catch(() => ({})))
      setStamp(Date.now())
    })
    source.onerror = () => {
      source.close()
      setError('Lost the progress stream. The job may still be running — reopen this product to check.')
    }
  }

  async function start(assetKeys = []) {
    setError(null)
    setEvents([])
    try {
      const { job_id } = await api.generate(product.id, assetKeys)
      setJob({ id: job_id, status: 'running', assets: {} })
      listen(job_id)
    } catch (e) {
      setError(e.message)
    }
  }

  async function cancel() {
    try {
      await api.cancelJob(job.id)
    } catch (e) {
      setError(e.message)
    }
  }

  if (!product?.id) return null

  const blocked = product.blockers?.length > 0

  return (
    <Panel
      title="Generate"
      action={
        running ? (
          <Button variant="danger" onClick={cancel}>
            Cancel
          </Button>
        ) : (
          <Button onClick={() => start()} disabled={blocked}>
            {Object.values(available).some(Boolean) ? 'Regenerate all' : 'Generate all 7 assets'}
          </Button>
        )
      }
    >
      <ErrorNote>{error}</ErrorNote>

      {blocked && (
        <p className="mb-4 text-xs text-amber-300">
          Resolve the outstanding items above before generating.
        </p>
      )}

      {(events.length > 0 || running) && (
        <div
          ref={logRef}
          className="mb-5 max-h-56 overflow-y-auto rounded border border-navy-soft/50 bg-midnight/70 p-3 font-mono text-xs"
        >
          {events.map((e, i) => (
            <div key={i} className={`flex gap-3 ${LEVEL_STYLE[e.level] || ''}`}>
              <span className="w-28 shrink-0 text-platinum-dim/70">{e.step}</span>
              <span className="min-w-0 break-words">{e.message}</span>
            </div>
          ))}
          {running && <div className="mt-1 text-platinum-dim">working…</div>}
        </div>
      )}

      {job && !running && (
        <div className="mb-4 flex items-center gap-3 text-sm">
          <StatusChip status={job.status} />
          {job.spend_inr > 0 && (
            <span className="text-platinum-dim">₹{job.spend_inr.toFixed(2)} spent</span>
          )}
          {job.error && <span className="text-red-300">{job.error}</span>}
        </div>
      )}

      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {assetTypes.map((asset) => {
          const result = job?.assets?.[asset.key]
          const has = available[asset.key]
          const check = result?.scale_check
          return (
            <li key={asset.key} className="overflow-hidden rounded border border-navy-soft/60">
              <div className="flex aspect-4/5 items-center justify-center bg-midnight/60">
                {has ? (
                  <img
                    src={api.assetImageUrl(product.id, asset.key, stamp)}
                    alt={asset.label}
                    className="size-full object-contain"
                  />
                ) : (
                  <span className="px-3 text-center text-xs text-platinum-dim">
                    {result?.error ? 'Failed' : 'Not generated'}
                  </span>
                )}
              </div>

              <div className="p-3">
                <p className="text-sm text-platinum">{asset.label}</p>
                <p className="mt-0.5 text-xs text-platinum-dim">
                  {asset.native_ratio} · {asset.pipeline}
                </p>

                {check && (
                  <p className={`mt-1 text-xs ${check.passed ? 'text-emerald-300' : 'text-amber-300'}`}>
                    {check.measured_mm.toFixed(1)} mm measured ·{' '}
                    {check.error_pct >= 0 ? '+' : ''}
                    {check.error_pct.toFixed(1)}%
                  </p>
                )}
                {result?.error && (
                  <p className="mt-1 text-xs break-words text-red-300">{result.error}</p>
                )}

                <div className="mt-3 flex gap-3 text-xs">
                  <button
                    type="button"
                    onClick={() => start([asset.key])}
                    disabled={running || blocked}
                    className="text-platinum-dim hover:text-platinum disabled:opacity-40"
                  >
                    Regenerate
                  </button>
                  {has && (
                    <a
                      href={api.assetImageUrl(product.id, asset.key, stamp)}
                      download={`${product.code}_${asset.key}.png`}
                      className="text-platinum-dim hover:text-platinum"
                    >
                      Download
                    </a>
                  )}
                </div>
              </div>
            </li>
          )
        })}
      </ul>
    </Panel>
  )
}
