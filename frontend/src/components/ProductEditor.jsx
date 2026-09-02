import { useEffect, useMemo, useState } from 'react'
import { api } from '../lib/api.js'
import AngleSlots from './AngleSlots.jsx'
import CutoutPanel from './CutoutPanel.jsx'
import DimensionFields from './DimensionFields.jsx'
import GeneratePanel from './GeneratePanel.jsx'
import { Button, ErrorNote, Field, Input, Panel, Select, Textarea } from './ui.jsx'

const BLANK = {
  code: '',
  name: '',
  category: 'earrings',
  description: '',
  concept: '',
  dimensions_mm: {},
}

export default function ProductEditor({ productId, onDone, onCancel }) {
  const [categories, setCategories] = useState([])
  const [form, setForm] = useState(BLANK)
  const [product, setProduct] = useState(null)
  const [staged, setStaged] = useState({})
  const [assetTypes, setAssetTypes] = useState([])
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)

  const isNew = !productId
  const category = useMemo(
    () => categories.find((c) => c.key === form.category),
    [categories, form.category],
  )

  useEffect(() => {
    api.categories().then(setCategories).catch((e) => setError(e.message))
    api.assetTypes().then(setAssetTypes).catch(() => {})
  }, [])

  useEffect(() => {
    if (!productId) return
    api
      .getProduct(productId)
      .then((p) => {
        setProduct(p)
        setForm({
          code: p.code,
          name: p.name,
          category: p.category,
          description: p.description,
          concept: p.concept,
          dimensions_mm: p.dimensions_mm,
        })
      })
      .catch((e) => setError(e.message))
  }, [productId])

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))

  function setDimension(key, raw) {
    setForm((f) => {
      const next = { ...f.dimensions_mm }
      if (raw === '') delete next[key]
      else next[key] = Number(raw)
      return { ...f, dimensions_mm: next }
    })
  }

  // Changing category invalidates dimensions — the keys differ per category and
  // the API rejects unknown ones, so clear rather than send a doomed payload.
  function setCategory(e) {
    const next = e.target.value
    setForm((f) => (f.category === next ? f : { ...f, category: next, dimensions_mm: {} }))
  }

  async function save(e) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      if (isNew) {
        const created = await api.createProduct(form)
        for (const [angle, file] of Object.entries(staged)) {
          if (file) await api.uploadAngle(created.id, angle, file)
        }
        onDone?.(created.id)
      } else {
        const { code, ...editable } = form
        await api.updateProduct(productId, editable)
        onDone?.(productId)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const blockers = product?.blockers ?? []

  return (
    <form onSubmit={save} className="grid gap-6">
      <Panel
        title={isNew ? 'New product' : `Edit ${product?.code ?? ''}`}
        action={
          <Button type="button" variant="ghost" onClick={onCancel}>
            Back
          </Button>
        }
      >
        <div className="grid gap-4">
          <ErrorNote>{error}</ErrorNote>

          <div className="grid gap-4 sm:grid-cols-3">
            <Field
              label="Product code"
              required
              hint={isNew ? 'e.g. E425. Used in output filenames.' : 'Code cannot be changed.'}
            >
              <Input
                value={form.code}
                onChange={set('code')}
                disabled={!isNew}
                placeholder="E425"
                required
              />
            </Field>

            <Field label="Name" required>
              <Input
                value={form.name}
                onChange={set('name')}
                placeholder="Cascade Drop Earrings"
                required
              />
            </Field>

            <Field label="Category" required hint="Selects the anatomical ruler used for scale.">
              <Select value={form.category} onChange={setCategory}>
                {categories.map((c) => (
                  <option key={c.key} value={c.key}>
                    {c.label}
                  </option>
                ))}
              </Select>
            </Field>
          </div>

          <Field label="Description" hint="Injected into every prompt. Materials, finish, stones.">
            <Textarea
              rows={2}
              value={form.description}
              onChange={set('description')}
              placeholder="Waterproof gold-tone with a freshwater pearl."
            />
          </Field>

          <Field
            label="Signature concept"
            hint="Optional. The creative idea for the hero campaign shot. Left blank, a default is used."
          >
            <Textarea
              rows={2}
              value={form.concept}
              onChange={set('concept')}
              placeholder="Emerging from still dark water, ripples breaking outward."
            />
          </Field>

          <DimensionFields
            category={category}
            values={form.dimensions_mm}
            onChange={setDimension}
          />
        </div>
      </Panel>

      <Panel title="Angles">
        <p className="mb-4 text-xs text-platinum-dim">
          Front is required. The others are optional but strongly recommended — the pipeline picks
          the best angle per asset type, and with only one angle every output uses the same view.
          {isNew && ' Files are staged and uploaded when you save.'}
        </p>
        <AngleSlots
          productId={productId}
          angles={product?.angles}
          staged={staged}
          onStage={(angle, file) =>
            setStaged((s) => {
              const next = { ...s }
              if (file) next[angle] = file
              else delete next[angle]
              return next
            })
          }
          onUploaded={setProduct}
        />
      </Panel>

      <CutoutPanel product={product} />

      {assetTypes.length > 0 && <GeneratePanel product={product} assetTypes={assetTypes} />}

      {blockers.length > 0 && (
        <div className="rounded border border-amber-400/40 bg-amber-950/25 px-4 py-3 text-sm text-amber-200">
          <p className="mb-1 font-medium">Not ready to generate</p>
          <ul className="list-inside list-disc text-amber-200/80">
            {blockers.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex items-center gap-3">
        <Button type="submit" disabled={saving}>
          {saving ? 'Saving…' : isNew ? 'Create product' : 'Save changes'}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  )
}
