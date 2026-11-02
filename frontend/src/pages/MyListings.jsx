import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { BookCover } from '../components/BookCard'
import { Alert, Button, Empty, Spinner, StatusBadge, formatPrice, timeAgo } from '../components/ui'

export default function MyListings() {
  const [books, setBooks] = useState(null)
  const [error, setError] = useState('')

  const load = () => api('/books/mine').then(setBooks).catch((e) => setError(e.message))
  useEffect(() => { load() }, [])

  const markSold = async (b) => {
    if (!confirm(`Mark "${b.title}" as sold outside the app? Anyone waiting will be told it's gone.`)) return
    try { await api(`/books/${b.id}/status`, { method: 'PATCH', body: { status: 'sold' } }); load() } catch (e) { setError(e.message) }
  }
  const remove = async (b) => {
    if (!confirm(`Delete "${b.title}"? This also removes its photos and any waiting requests.`)) return
    try { await api(`/books/${b.id}`, { method: 'DELETE' }); load() } catch (e) { setError(e.message) }
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-3xl font-bold">My listings</h1>
        <Link to="/sell"><Button variant="accent">+ Sell a book</Button></Link>
      </div>
      <Alert className="mb-3">{error}</Alert>
      {!books ? <Spinner className="mt-12" /> : books.length === 0 ? (
        <Empty title="You haven't listed anything yet">Got last semester's books lying around? List them in a minute.</Empty>
      ) : (
        <ul className="space-y-3">
          {books.map((b) => (
            <li key={b.id} className="flex flex-wrap items-center gap-3 rounded-xl border border-line bg-surface p-3">
              <Link to={`/books/${b.id}`}><BookCover book={b} className="h-16 w-20 rounded-lg" /></Link>
              <div className="min-w-0 flex-1">
                <Link to={`/books/${b.id}`} className="font-medium hover:underline">{b.title}</Link>
                <p className="text-sm text-ink-soft">{formatPrice(b.price)} · listed {timeAgo(b.created_at)}</p>
              </div>
              <StatusBadge status={b.status} />
              <div className="flex gap-2">
                {b.status !== 'sold' && <Link to={`/books/${b.id}/edit`}><Button variant="secondary">Edit</Button></Link>}
                {b.status === 'available' && <Button variant="secondary" onClick={() => markSold(b)}>Sold elsewhere</Button>}
                {b.status === 'reserved' && <Link to="/messages?role=seller"><Button variant="secondary">See deal</Button></Link>}
                {b.status !== 'reserved' && <Button variant="danger" onClick={() => remove(b)}>Delete</Button>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
