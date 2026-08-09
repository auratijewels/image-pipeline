import { Field, Input } from './ui.jsx'

/**
 * Dimension inputs, driven entirely by /api/categories.
 *
 * Which measurements a category needs — and which one drives scale — lives in
 * the backend's config/dimensions.py. Adding a category should never mean
 * editing this file.
 */
export default function DimensionFields({ category, values, onChange, errors = {} }) {
  if (!category) return null

  return (
    <fieldset>
      <legend className="mb-1 text-sm text-platinum">Dimensions</legend>
      <p className="mb-3 text-xs text-platinum-dim">
        In millimetres. These drive the scale pipeline — an error here shows up in every
        on-model shot.
      </p>
      <div className="grid gap-4 sm:grid-cols-2">
        {category.dimensions.map((d) => (
          <Field
            key={d.key}
            label={
              <>
                {d.label}
                {d.primary && (
                  <span className="ml-2 rounded-full border border-sky-400/40 px-2 py-0.5 text-[10px] tracking-wide text-sky-300 uppercase">
                    drives scale
                  </span>
                )}
              </>
            }
            required={d.required}
            hint={d.hint}
            error={errors[d.key]}
          >
            <div className="relative">
              <Input
                type="number"
                min="0"
                step="0.1"
                inputMode="decimal"
                placeholder="0.0"
                value={values[d.key] ?? ''}
                onChange={(e) => onChange(d.key, e.target.value)}
                className="pr-10"
              />
              <span className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-xs text-platinum-dim">
                mm
              </span>
            </div>
          </Field>
        ))}
      </div>
    </fieldset>
  )
}
