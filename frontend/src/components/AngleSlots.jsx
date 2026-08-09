import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api.js'

const SLOTS = [
  { angle: 'front', label: 'Front', required: true, hint: 'The hero angle. Used for catalog shots.' },
  { angle: 'back', label: 'Back', hint: 'Clasp, post or reverse detail.' },
  { angle: 'left', label: 'Left', hint: 'Profile. Preferred for on-ear shots.' },
  { angle: 'right', label: 'Right', hint: 'Opposite profile.' },
  { angle: 'extra', label: 'Extra', hint: 'Scale reference or macro detail.' },
]

/**
 * Five labelled drop targets.
 *
 * Works in two modes. For a saved product, `productId` is set and each drop
 * uploads immediately. For an unsaved one, files are staged in memory and the
 * editor uploads them after the product exists — a product id is required
 * before the API will take an angle.
 */
export default function AngleSlots({ productId, angles = {}, staged = {}, onStage, onUploaded }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {SLOTS.map((slot) => (
        <Slot
          key={slot.angle}
          {...slot}
          productId={productId}
          uploaded={angles[slot.angle]}
          stagedFile={staged[slot.angle]}
          onStage={onStage}
          onUploaded={onUploaded}
        />
      ))}
    </div>
  )
}

function Slot({ angle, label, hint, required, productId, uploaded, stagedFile, onStage, onUploaded }) {
  const inputRef = useRef(null)
  const [over, setOver] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [preview, setPreview] = useState(null)

  useEffect(() => {
    if (!stagedFile) return setPreview(null)
    const url = URL.createObjectURL(stagedFile)
    setPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [stagedFile])

  async function accept(file) {
    if (!file) return
    setError(null)
    if (!productId) {
      onStage?.(angle, file)
      return
    }
    setBusy(true)
    try {
      onUploaded?.(await api.uploadAngle(productId, angle, file))
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function clear(e) {
    e.stopPropagation()
    setError(null)
    if (!productId || !uploaded) return onStage?.(angle, null)
    setBusy(true)
    try {
      onUploaded?.(await api.deleteAngle(productId, angle))
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const src = uploaded
    ? `/api/products/${productId}/angles/${angle}/raw?v=${encodeURIComponent(uploaded.uploaded_at)}`
    : preview
  const filled = Boolean(src)

  return (
    <div>
      <div
        role="button"
        tabIndex={0}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault()
          setOver(true)
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setOver(false)
          accept(e.dataTransfer.files?.[0])
        }}
        className={`relative flex aspect-square cursor-pointer items-center justify-center overflow-hidden rounded border-2 border-dashed transition-colors ${
          over
            ? 'border-platinum bg-platinum/10'
            : filled
              ? 'border-navy-soft bg-midnight/60'
              : 'border-navy-soft/70 bg-midnight/30 hover:border-platinum/50'
        }`}
      >
        {filled ? (
          <>
            <img src={src} alt={`${label} angle`} className="size-full object-cover" />
            <button
              type="button"
              onClick={clear}
              aria-label={`Remove ${label} image`}
              className="absolute top-1.5 right-1.5 rounded bg-midnight/85 px-1.5 py-0.5 text-xs text-platinum hover:bg-red-900/85"
            >
              ✕
            </button>
          </>
        ) : (
          <span className="px-2 text-center text-xs text-platinum-dim">
            {busy ? 'Uploading…' : 'Drop or click'}
          </span>
        )}
        {busy && filled && <div className="absolute inset-0 bg-midnight/60" />}
      </div>

      <div className="mt-1.5 flex items-baseline gap-1.5">
        <span className="text-sm text-platinum">{label}</span>
        {required && <span className="text-xs text-amber-400/80">required</span>}
        {!productId && stagedFile && <span className="text-xs text-sky-300">staged</span>}
      </div>
      <p className="mt-0.5 text-xs text-platinum-dim">{error ? '' : hint}</p>
      {error && <p className="mt-0.5 text-xs text-red-300">{error}</p>}

      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp,image/tiff"
        className="hidden"
        onChange={(e) => {
          accept(e.target.files?.[0])
          e.target.value = ''
        }}
      />
    </div>
  )
}

export { SLOTS }
