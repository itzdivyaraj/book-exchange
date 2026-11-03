// Inbox (list of conversations) and Chat (one conversation, polling for new messages).
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { ReportForm } from '../components/Extras'
import { Alert, Button, Empty, Spinner, StatusBadge, formatPrice, timeAgo } from '../components/ui'

const other = (r) => (r.my_role === 'buyer' ? r.seller : r.buyer)

export function Inbox() {
  const [params, setParams] = useSearchParams()
  const role = params.get('role') || 'all'
  const [rows, setRows] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    setRows(null)
    api('/conversations', { params: { role } }).then(setRows).catch((e) => setError(e.message))
  }, [role])

  const tab = (value, label) => (
    <button
      onClick={() => setParams(value === 'all' ? {} : { role: value })}
      className={`rounded-lg px-3 py-1.5 text-sm font-medium ${role === value ? 'bg-ink text-paper' : 'text-ink-soft hover:bg-black/5'}`}
    >
      {label}
    </button>
  )

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-3xl font-bold">Messages</h1>
      <div className="my-4 flex gap-1">{tab('all', 'All')}{tab('buyer', 'Buying')}{tab('seller', 'Selling')}</div>
      <Alert>{error}</Alert>
      {!rows ? <Spinner className="mt-12" /> : rows.length === 0 ? (
        <Empty title="No conversations yet">When you message a seller, or someone messages you about your book, the chat appears here.</Empty>
      ) : (
        <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface">
          {rows.map((r) => (
            <li key={r.id}>
              <Link to={`/messages/${r.id}`} className="flex items-center gap-3 p-3 hover:bg-paper/60">
                {r.book.image_url ? (
                  <img src={r.book.image_url} alt="" className="h-12 w-12 shrink-0 rounded-lg object-cover" />
                ) : (
                  <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-ink font-display text-paper">{r.book.title[0]}</div>
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className={`truncate ${r.unread_count ? 'font-semibold' : 'font-medium'}`}>{r.book.title}</span>
                    {r.book.status === 'sold' && <StatusBadge status="sold" />}
                  </div>
                  <p className="truncate text-sm text-ink-soft">
                    {r.my_role === 'buyer' ? 'Seller' : 'Buyer'}: {other(r).name}
                    {r.last_message && <> · {r.last_message.is_mine ? 'You: ' : ''}{r.last_message.body}</>}
                  </p>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1">
                  <span className="text-xs text-ink-soft">{timeAgo(r.updated_at)}</span>
                  {r.unread_count > 0 && <span className="rounded-full bg-accent px-2 py-0.5 text-xs font-medium text-white">{r.unread_count}</span>}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

const POLL_MS = 4000 // check for new messages every 4 seconds

export function Chat() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [req, setReq] = useState(null)
  const [messages, setMessages] = useState([])
  const [text, setText] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [reporting, setReporting] = useState(false)
  const lastId = useRef(null)
  const bottom = useRef()

  // POLLING: ask only for messages newer than the last one we have.
  const poll = useCallback(async () => {
    const fresh = await api(`/conversations/${id}/messages`, { params: { after_id: lastId.current } })
    if (fresh.length) {
      lastId.current = Math.max(lastId.current ?? 0, fresh[fresh.length - 1].id)
      // Two checks can overlap (e.g. right after sending). Skip messages we already have.
      setMessages((m) => {
        const seen = new Set(m.map((x) => x.id))
        return [...m, ...fresh.filter((x) => !seen.has(x.id))]
      })
    }
    return fresh.length
  }, [id])

  const loadRequest = useCallback(() => api(`/conversations/${id}`).then(setReq), [id])

  useEffect(() => {
    lastId.current = null
    setMessages([])
    setReq(null)
    loadRequest().catch((e) => setError(e.message))
    poll().catch(() => {})
    let tick = 0
    const timer = setInterval(() => {
      if (document.hidden) return // don't poll while the tab is in the background
      poll().then((n) => { if (n || ++tick % 3 === 0) loadRequest() }).catch(() => {})
    }, POLL_MS)
    return () => clearInterval(timer)
  }, [id, poll, loadRequest])

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: 'end' }) // (braces: an effect may only return a clean-up function)
  }, [messages.length])

  const send = async (e) => {
    e.preventDefault()
    if (!text.trim()) return
    setBusy('send')
    setError('')
    try {
      await api(`/conversations/${id}/messages`, { method: 'POST', body: { body: text } })
      setText('')
      await poll()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy('')
    }
  }

  const block = async () => {
    if (!confirm(`Block ${other(req).name}? Neither of you will be able to message the other.`)) return
    try { await api(`/blocks/${other(req).id}`, { method: 'POST' }); navigate('/messages') } catch (e) { setError(e.message) }
  }

  if (error && !req) return <Alert>{error}</Alert>
  if (!req) return <Spinner className="mt-24" />

  const seller = req.my_role === 'seller'

  return (
    <div className="mx-auto flex max-w-3xl flex-col" style={{ minHeight: 'calc(100vh - 180px)' }}>
      <div className="rounded-xl border border-line bg-surface p-3">
        <div className="flex flex-wrap items-center gap-3">
          <Link to="/messages" className="text-sm text-ink-soft hover:text-ink">← Inbox</Link>
          <div className="min-w-0 flex-1">
            <Link to={`/books/${req.book.id}`} className="font-medium hover:underline">{req.book.title}</Link>
            <p className="text-sm text-ink-soft">{formatPrice(req.book.price)} · {seller ? 'Buyer' : 'Seller'}: {other(req).name}</p>
          </div>
          {req.book.status === 'sold' && <StatusBadge status="sold" />}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-3 border-t border-line pt-3 text-xs">
          <span className="flex-1 text-ink-soft">
            {req.book.status === 'sold'
              ? 'The seller has marked this book as sold.'
              : `Pickup in ${req.book.city}. Agree on the details here.`}
          </span>
          <button className="text-ink-soft hover:text-red-700 hover:underline" onClick={() => setReporting(!reporting)}>Report</button>
          <button className="text-ink-soft hover:text-red-700 hover:underline" onClick={block}>Block</button>
        </div>
        {reporting && <div className="mt-3"><ReportForm userId={other(req).id} onClose={() => setReporting(false)} /></div>}
      </div>

      <div className="flex-1 space-y-2 py-4" aria-live="polite">
        {messages.map((m) =>
          m.is_system ? (
            <p
              key={m.id}
              className="mx-auto max-w-md rounded-lg bg-amber-50 px-3 py-2 text-center text-xs text-amber-900 whitespace-pre-line"
            >
              {m.body}
            </p>
          ) : (
            <div key={m.id} className={`flex ${m.is_mine ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[80%] rounded-2xl px-3 py-2 text-sm ${m.is_mine ? 'rounded-br-sm bg-ink text-paper' : 'rounded-bl-sm border border-line bg-surface'}`}>
                <p className="whitespace-pre-line break-words">{m.body}</p>
                <p className={`mt-0.5 text-[10px] ${m.is_mine ? 'text-paper/60' : 'text-ink-soft'}`}>{timeAgo(m.created_at)}</p>
              </div>
            </div>
          ),
        )}
        <div ref={bottom} />
      </div>

      <Alert className="mb-2">{error}</Alert>
      <form onSubmit={send} className="sticky bottom-0 flex gap-2 border-t border-line bg-paper py-3">
          <input
            className="flex-1 rounded-lg border border-line bg-surface px-3 py-2 text-sm focus:border-ink focus:outline-none"
            placeholder="Write a message…"
            maxLength={1000}
            value={text}
            onChange={(e) => setText(e.target.value)}
            aria-label="Message"
          />
          <Button type="submit" loading={busy === 'send'} disabled={!text.trim()}>Send</Button>
        </form>
    </div>
  )
}
