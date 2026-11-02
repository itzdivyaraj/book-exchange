// Pagination + the report form, used on a few pages.
import { useState } from 'react'
import { api } from '../api'
import { Alert, Button, Select, Textarea } from './ui'

export function Pagination({ page, pages, onPage }) {
  if (pages <= 1) return null
  return (
    <div className="mt-6 flex items-center justify-center gap-3 text-sm">
      <Button variant="secondary" disabled={page <= 1} onClick={() => onPage(page - 1)}>← Previous</Button>
      <span className="text-ink-soft">Page {page} of {pages}</span>
      <Button variant="secondary" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next →</Button>
    </div>
  )
}

const REASONS = {
  scam: 'Scam (asked for advance payment, fake listing…)',
  spam: 'Spam',
  inappropriate: 'Inappropriate',
  wrong_info: 'Wrong information',
  other: 'Something else',
}

export function ReportForm({ bookId, userId, onClose }) {
  const [reason, setReason] = useState('scam')
  const [details, setDetails] = useState('')
  const [state, setState] = useState({ busy: false, error: '', done: '' })

  const submit = async () => {
    setState({ busy: true, error: '', done: '' })
    try {
      const r = await api('/reports', { method: 'POST', body: { book_id: bookId, user_id: userId, reason, details: details || null } })
      setState({ busy: false, error: '', done: r.detail })
    } catch (e) {
      setState({ busy: false, error: e.message, done: '' })
    }
  }

  return (
    <div className="space-y-2 rounded-lg border border-line bg-paper/60 p-3">
      {state.done ? (
        <>
          <Alert kind="success">{state.done}</Alert>
          <Button variant="ghost" onClick={onClose}>Close</Button>
        </>
      ) : (
        <>
          <p className="text-sm font-medium">What's wrong?</p>
          <Select value={reason} onChange={(e) => setReason(e.target.value)}>
            {Object.entries(REASONS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
          <Textarea placeholder="Details (optional)" value={details} maxLength={1000} onChange={(e) => setDetails(e.target.value)} />
          <Alert>{state.error}</Alert>
          <div className="flex gap-2">
            <Button variant="danger" loading={state.busy} onClick={submit}>Send report</Button>
            <Button variant="ghost" onClick={onClose}>Cancel</Button>
          </div>
        </>
      )}
    </div>
  )
}
