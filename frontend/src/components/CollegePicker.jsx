// Search-as-you-type college picker with "add my college" and "did you mean...?".
import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { Alert, Button, Input } from './ui'

export default function CollegePicker({ value, onChange, allowAdd = true, placeholder = 'Start typing: DU, JNU, IIT Delhi…' }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [open, setOpen] = useState(false)
  const [adding, setAdding] = useState(false)
  const timer = useRef()

  // Wait 250ms after the last keystroke before searching (fewer server calls while typing).
  useEffect(() => {
    clearTimeout(timer.current)
    if (!query.trim()) return setResults([])
    timer.current = setTimeout(() => {
      api('/colleges', { params: { q: query } }).then(setResults).catch(() => setResults([]))
    }, 250)
    return () => clearTimeout(timer.current)
  }, [query])

  if (value) {
    return (
      <div className="flex items-center justify-between gap-2 rounded-lg border border-line bg-surface px-3 py-2 text-sm">
        <span>
          <span className="font-medium">{value.name}</span>
          {value.city && <span className="text-ink-soft"> · {value.city}</span>}
        </span>
        <button type="button" className="text-xs font-medium text-accent-dark hover:underline" onClick={() => onChange(null)}>
          Change
        </button>
      </div>
    )
  }

  if (adding) {
    return (
      <AddCollege
        initialName={query}
        onDone={(c) => {
          setAdding(false)
          if (c) onChange(c)
        }}
      />
    )
  }

  return (
    <div className="relative">
      <Input
        value={query}
        onChange={(e) => {
          setQuery(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder={placeholder}
        aria-label="College"
        role="combobox"
        aria-expanded={open}
      />
      {open && query.trim() && (
        <ul className="absolute z-30 mt-1 max-h-72 w-full overflow-auto rounded-lg border border-line bg-surface py-1 shadow-lg" role="listbox">
          {results.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                role="option"
                className="block w-full px-3 py-2 text-left text-sm hover:bg-paper"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  onChange(c)
                  setQuery('')
                }}
              >
                <span className="font-medium">{c.name}</span>
                {c.city && <span className="text-ink-soft"> · {c.city}</span>}
              </button>
            </li>
          ))}
          {results.length === 0 && <li className="px-3 py-2 text-sm text-ink-soft">No matches yet.</li>}
          {allowAdd && (
            <li className="border-t border-line">
              <button
                type="button"
                className="block w-full px-3 py-2 text-left text-sm font-medium text-accent-dark hover:bg-paper"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => setAdding(true)}
              >
                Can't find your college? Add it
              </button>
            </li>
          )}
        </ul>
      )}
    </div>
  )
}

function AddCollege({ initialName, onDone }) {
  const [form, setForm] = useState({ name: initialName, city: '', state: '' })
  const [suggestions, setSuggestions] = useState([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (confirmNew = false) => {
    setBusy(true)
    setError('')
    try {
      const r = await api('/colleges', { method: 'POST', body: { ...form, state: form.state || null, confirm_new: confirmNew } })
      if (r.college) return onDone(r.college) // created, or it already existed under another name
      setSuggestions(r.suggestions)           // close matches: ask "did you mean...?"
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-2 rounded-lg border border-line bg-paper/60 p-3">
      <p className="text-sm font-medium">Add your college</p>
      <Input placeholder="Full college name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
      <div className="grid grid-cols-2 gap-2">
        <Input placeholder="City *" value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} />
        <Input placeholder="State" value={form.state} onChange={(e) => setForm({ ...form, state: e.target.value })} />
      </div>
      <Alert>{error}</Alert>
      {suggestions.length > 0 ? (
        <div className="space-y-2">
          <p className="text-sm">Did you mean one of these?</p>
          {suggestions.map((c) => (
            <button key={c.id} type="button" className="block w-full rounded-lg border border-line bg-surface px-3 py-2 text-left text-sm hover:border-ink/40" onClick={() => onDone(c)}>
              {c.name} {c.city && <span className="text-ink-soft">· {c.city}</span>}
            </button>
          ))}
          <Button type="button" variant="secondary" loading={busy} onClick={() => submit(true)}>
            No, mine is different, add it
          </Button>
        </div>
      ) : (
        <div className="flex gap-2">
          <Button type="button" loading={busy} disabled={form.name.trim().length < 3 || form.city.trim().length < 2} onClick={() => submit(false)}>
            Add college
          </Button>
          <Button type="button" variant="ghost" onClick={() => onDone(null)}>Cancel</Button>
        </div>
      )}
    </div>
  )
}
