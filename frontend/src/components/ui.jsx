export function Panel({ title, action, children }) {
  return (
    <section className="rounded-lg border border-navy-soft/60 bg-navy/30 p-6">
      {(title || action) && (
        <div className="mb-5 flex items-baseline justify-between gap-4">
          <h2 className="font-display text-2xl font-light tracking-wide text-platinum">{title}</h2>
          {action}
        </div>
      )}
      {children}
    </section>
  )
}

export function Button({ variant = 'primary', className = '', ...props }) {
  const styles = {
    primary: 'bg-platinum text-midnight hover:bg-white disabled:bg-navy-soft disabled:text-platinum-dim',
    ghost: 'border border-navy-soft text-platinum hover:border-platinum/70 disabled:text-platinum-dim',
    danger: 'border border-red-500/50 text-red-300 hover:bg-red-950/40',
  }[variant]
  return (
    <button
      className={`rounded px-4 py-2 text-sm font-medium tracking-wide transition-colors disabled:cursor-not-allowed ${styles} ${className}`}
      {...props}
    />
  )
}

export function Field({ label, hint, error, required, children }) {
  return (
    <label className="block">
      <span className="mb-1.5 flex items-baseline gap-2 text-sm text-platinum">
        {label}
        {required && <span className="text-amber-400/80">*</span>}
      </span>
      {children}
      {hint && !error && <span className="mt-1 block text-xs text-platinum-dim">{hint}</span>}
      {error && <span className="mt-1 block text-xs text-red-300">{error}</span>}
    </label>
  )
}

const inputBase =
  'w-full rounded border border-navy-soft bg-midnight/60 px-3 py-2 text-sm text-platinum ' +
  'placeholder:text-platinum-dim/60 focus:border-platinum/60 focus:outline-none'

export function Input(props) {
  return <input className={inputBase} {...props} />
}

export function Textarea(props) {
  return <textarea className={`${inputBase} resize-y`} {...props} />
}

export function Select(props) {
  return <select className={inputBase} {...props} />
}

export function StatusChip({ status }) {
  const tone =
    {
      draft: 'border-amber-400/40 text-amber-300',
      ready: 'border-emerald-400/40 text-emerald-300',
      generating: 'border-sky-400/40 text-sky-300',
      complete: 'border-platinum/40 text-platinum',
      failed: 'border-red-400/40 text-red-300',
    }[status] || 'border-navy-soft text-platinum-dim'
  return (
    <span className={`rounded-full border px-2.5 py-0.5 text-xs tracking-wide uppercase ${tone}`}>
      {status}
    </span>
  )
}

export function ErrorNote({ children }) {
  if (!children) return null
  return (
    <div className="rounded border border-red-500/40 bg-red-950/40 px-4 py-3 text-sm text-red-200">
      {children}
    </div>
  )
}
