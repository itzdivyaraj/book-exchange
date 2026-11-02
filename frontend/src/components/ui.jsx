// Small reusable building blocks so every page looks consistent.

export function Button({ variant = 'primary', loading = false, className = '', children, disabled, ...props }) {
  const styles = {
    primary: 'bg-ink text-paper hover:bg-ink/90',
    accent: 'bg-accent text-white hover:bg-accent-dark',
    secondary: 'bg-white text-ink border border-line hover:border-ink/40',
    danger: 'bg-white text-red-700 border border-red-200 hover:bg-red-50',
    ghost: 'text-ink-soft hover:text-ink hover:bg-black/5',
  }
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${styles[variant]} ${className}`}
      // Disabled while loading: a double-click can't send the same request twice.
      disabled={disabled || loading}
      {...props}
    >
      {loading && <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />}
      {children}
    </button>
  )
}

const fieldClass =
  'w-full rounded-lg border border-line bg-white px-3 py-2 text-sm text-ink placeholder:text-ink-soft/60 focus:border-ink focus:outline-none focus:ring-2 focus:ring-ink/10'

export function Field({ label, hint, children }) {
  return (
    <label className="block">
      {label && <span className="mb-1 block text-sm font-medium text-ink">{label}</span>}
      {children}
      {hint && <span className="mt-1 block text-xs text-ink-soft">{hint}</span>}
    </label>
  )
}

export const Input = (props) => <input className={fieldClass} {...props} />
export const Textarea = (props) => <textarea className={fieldClass} rows={3} {...props} />
export const Select = ({ children, ...props }) => (
  <select className={fieldClass} {...props}>
    {children}
  </select>
)

export function Alert({ kind = 'error', children, className = '' }) {
  if (!children) return null
  const styles = {
    error: 'border-red-200 bg-red-50 text-red-800',
    success: 'border-emerald-200 bg-emerald-50 text-emerald-800',
    info: 'border-amber-200 bg-amber-50 text-amber-900',
  }
  return (
    <div role={kind === 'error' ? 'alert' : 'status'} className={`rounded-lg border px-3 py-2 text-sm ${styles[kind]} ${className}`}>
      {children}
    </div>
  )
}

export function Spinner({ className = '' }) {
  return (
    <div className={`flex justify-center ${className}`}>
      <span className="h-6 w-6 animate-spin rounded-full border-2 border-ink/30 border-t-ink" aria-label="Loading" />
    </div>
  )
}

export function Card({ className = '', children }) {
  return <div className={`rounded-xl border border-line bg-white p-5 ${className}`}>{children}</div>
}

export function Empty({ title, children }) {
  return (
    <div className="rounded-xl border border-dashed border-line bg-white/60 px-6 py-12 text-center">
      <p className="font-display text-lg">{title}</p>
      {children && <div className="mt-2 text-sm text-ink-soft">{children}</div>}
    </div>
  )
}

const STATUS_STYLES = {
  available: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  reserved: 'bg-amber-50 text-amber-800 border-amber-200',
  sold: 'bg-stone-100 text-stone-600 border-stone-200',
  pending: 'bg-sky-50 text-sky-700 border-sky-200',
  accepted: 'bg-amber-50 text-amber-800 border-amber-200',
  completed: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  rejected: 'bg-stone-100 text-stone-600 border-stone-200',
  cancelled: 'bg-stone-100 text-stone-600 border-stone-200',
}

export function StatusBadge({ status }) {
  return (
    <span className={`inline-block rounded-full border px-2 py-0.5 text-xs font-medium capitalize ${STATUS_STYLES[status] || ''}`}>
      {status}
    </span>
  )
}

export const CONDITIONS = {
  like_new: 'Like new',
  good: 'Good',
  fair: 'Fair',
  poor: 'Poor',
}

export const formatPrice = (p) => (p === 0 ? 'Free' : `₹${p.toLocaleString('en-IN')}`)

export function timeAgo(iso) {
  const s = (Date.now() - new Date(iso).getTime()) / 1000
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  if (s < 86400 * 7) return `${Math.floor(s / 86400)}d ago`
  return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
}
