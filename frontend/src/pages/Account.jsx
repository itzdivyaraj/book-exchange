// Profile, change password, blocked people, delete account.
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, setToken } from '../api'
import { useAuth } from '../auth'
import { Alert, Button, Card, Field, Input } from '../components/ui'

export default function Account() {
  const { user, setUser } = useAuth()
  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <h1 className="text-3xl font-bold">Your account</h1>
      <Card>
        <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
          <dt className="text-ink-soft">Name</dt><dd>{user.name}</dd>
          <dt className="text-ink-soft">Email</dt><dd>{user.email} {user.email_verified ? <span className="text-emerald-700">✓ verified</span> : <span className="text-amber-700">not verified</span>}</dd>
          <dt className="text-ink-soft">College</dt><dd>{user.college.name}</dd>
        </dl>
      </Card>
      <ChangePassword />
      <Blocked />
      <DeleteAccount onDeleted={() => setUser(null)} />
    </div>
  )
}

function ChangePassword() {
  const [form, setForm] = useState({ current_password: '', new_password: '' })
  const [msg, setMsg] = useState({ kind: 'error', text: '' })
  const [busy, setBusy] = useState(false)
  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setMsg({ kind: 'error', text: '' })
    try {
      const r = await api('/auth/change-password', { method: 'POST', body: form })
      setMsg({ kind: 'success', text: r.detail })
      setForm({ current_password: '', new_password: '' })
    } catch (err) {
      setMsg({ kind: 'error', text: err.message })
    } finally {
      setBusy(false)
    }
  }
  return (
    <Card>
      <h2 className="text-xl font-bold">Change password</h2>
      <form onSubmit={submit} className="mt-3 grid gap-3 sm:grid-cols-2">
        <Field label="Current password"><Input type="password" required autoComplete="current-password" value={form.current_password} onChange={(e) => setForm({ ...form, current_password: e.target.value })} /></Field>
        <Field label="New password"><Input type="password" required minLength={8} maxLength={72} autoComplete="new-password" value={form.new_password} onChange={(e) => setForm({ ...form, new_password: e.target.value })} /></Field>
        <div className="space-y-2 sm:col-span-2">
          <Alert kind={msg.kind}>{msg.text}</Alert>
          <Button type="submit" loading={busy}>Change password</Button>
        </div>
      </form>
    </Card>
  )
}

function Blocked() {
  const [rows, setRows] = useState([])
  const load = () => api('/blocks').then(setRows).catch(() => {})
  useEffect(() => { load() }, [])
  return (
    <Card>
      <h2 className="text-xl font-bold">Blocked people</h2>
      {rows.length === 0 ? (
        <p className="mt-2 text-sm text-ink-soft">You haven't blocked anyone.</p>
      ) : (
        <ul className="mt-2 divide-y divide-line">
          {rows.map((b) => (
            <li key={b.id} className="flex items-center justify-between py-2 text-sm">
              {b.name}
              <Button variant="ghost" onClick={async () => { await api(`/blocks/${b.id}`, { method: 'DELETE' }); load() }}>Unblock</Button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

function DeleteAccount({ onDeleted }) {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [password, setPassword] = useState('')
  const [confirmText, setConfirmText] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await api('/auth/delete-account', { method: 'POST', body: { password } })
      setToken(null)
      onDeleted()
      navigate('/', { replace: true })
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }
  return (
    <Card className="border-red-200">
      <h2 className="text-xl font-bold text-red-800">Delete account</h2>
      <p className="mt-1 text-sm text-ink-soft">
        Your name, email and messages are erased, and your unsold listings and all your photos are deleted. People you were chatting with will see that you left. This can't be undone.
      </p>
      {!open ? (
        <Button variant="danger" className="mt-3" onClick={() => setOpen(true)}>Delete my account…</Button>
      ) : (
        <form onSubmit={submit} className="mt-3 space-y-3">
          <Field label="Your password"><Input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
          <Field label='Type "DELETE" to confirm'><Input value={confirmText} onChange={(e) => setConfirmText(e.target.value)} /></Field>
          <Alert>{error}</Alert>
          <div className="flex gap-2">
            <Button type="submit" variant="danger" loading={busy} disabled={confirmText !== 'DELETE'}>Permanently delete</Button>
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
          </div>
        </form>
      )}
    </Card>
  )
}
