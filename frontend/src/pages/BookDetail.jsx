// One book: photos, details, and what you can do (request / edit / report / block).
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { BookCover } from '../components/BookCard'
import { ReportForm } from '../components/Extras'
import { Alert, Button, CONDITIONS, Card, Spinner, StatusBadge, Textarea, formatPrice, timeAgo } from '../components/ui'

export default function BookDetail() {
  const { id } = useParams()
  const { user } = useAuth()
  const navigate = useNavigate()
  const [book, setBook] = useState(null)
  const [error, setError] = useState('')
  const [photo, setPhoto] = useState(0)
  const [message, setMessage] = useState('Hi! Is this still available?')
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  const [reporting, setReporting] = useState(false)

  useEffect(() => {
    setBook(null)
    api(`/books/${id}`).then(setBook).catch((e) => setError(e.message))
  }, [id, user])

  if (error) return <Alert>{error}</Alert>
  if (!book) return <Spinner className="mt-24" />

  const request = async () => {
    setBusy(true)
    setActionError('')
    try {
      const r = await api('/requests', { method: 'POST', body: { book_id: book.id, message } })
      navigate(`/messages/${r.id}`)
    } catch (e) {
      setActionError(e.message)
      setBusy(false)
    }
  }

  const block = async () => {
    if (!confirm(`Block ${book.seller.name}? You won't see each other's listings or messages.`)) return
    try {
      await api(`/blocks/${book.seller.id}`, { method: 'POST' })
      navigate('/')
    } catch (e) {
      setActionError(e.message)
    }
  }

  const images = book.images
  return (
    <div className="grid gap-6 md:grid-cols-2">
      <div>
        {images.length ? (
          <>
            <img src={images[photo]?.url} alt={book.title} className="aspect-[4/3] w-full rounded-xl border border-line bg-surface object-contain" />
            {images.length > 1 && (
              <div className="mt-2 flex gap-2">
                {images.map((img, i) => (
                  <button key={img.id} onClick={() => setPhoto(i)} className={`overflow-hidden rounded-lg border-2 ${i === photo ? 'border-ink' : 'border-transparent'}`}>
                    <img src={img.url} alt="" className="h-16 w-20 object-cover" />
                  </button>
                ))}
              </div>
            )}
          </>
        ) : (
          <BookCover book={book} className="aspect-[4/3] w-full rounded-xl" />
        )}
      </div>

      <div className="space-y-4">
        <div>
          <div className="flex items-center gap-2">
            <StatusBadge status={book.status} />
            <span className="text-xs text-ink-soft">Listed {timeAgo(book.created_at)}</span>
          </div>
          <h1 className="mt-2 text-3xl font-bold leading-tight">{book.title}</h1>
          <p className="text-ink-soft">by {book.author}{book.edition && ` · ${book.edition} edition`}</p>
          <p className="mt-3 font-display text-3xl font-bold text-accent-dark">{formatPrice(book.price)}</p>
        </div>

        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 rounded-xl border border-line bg-surface p-4 text-sm">
          <dt className="text-ink-soft">Condition</dt><dd>{CONDITIONS[book.condition]}</dd>
          {book.subject && <><dt className="text-ink-soft">Subject</dt><dd>{book.subject}</dd></>}
          {book.semester && <><dt className="text-ink-soft">Semester</dt><dd>{book.semester}</dd></>}
          {book.isbn && <><dt className="text-ink-soft">ISBN</dt><dd>{book.isbn}</dd></>}
          <dt className="text-ink-soft">Seller</dt><dd>{book.seller.name}</dd>
          <dt className="text-ink-soft">College</dt><dd>{book.college.name}</dd>
        </dl>
        {book.description && <p className="whitespace-pre-line text-sm leading-relaxed">{book.description}</p>}

        <Alert>{actionError}</Alert>

        {book.is_mine ? (
          <Card className="space-y-2">
            <p className="text-sm text-ink-soft">This is your listing.</p>
            {book.status !== 'sold' && <Link to={`/books/${book.id}/edit`}><Button className="w-full">Edit listing & photos</Button></Link>}
            <Link to="/my-listings" className="block text-center text-sm text-accent-dark hover:underline">Manage in My listings</Link>
          </Card>
        ) : !user ? (
          <Card>
            <p className="text-sm">Want this book?</p>
            <Link to={`/login?next=/books/${book.id}`}><Button variant="accent" className="mt-2 w-full">Log in to request it</Button></Link>
          </Card>
        ) : book.status !== 'available' ? (
          <Alert kind="info">This book is {book.status}, so it can't be requested right now.</Alert>
        ) : !user.email_verified ? (
          <Alert kind="info">Verify your email to request books. <Link to="/verify" className="font-semibold underline">Enter your code</Link></Alert>
        ) : (
          <Card className="space-y-2">
            <p className="text-sm font-medium">Message the seller</p>
            <Textarea value={message} maxLength={1000} onChange={(e) => setMessage(e.target.value)} />
            <Button variant="accent" loading={busy} className="w-full" onClick={request}>Request to buy</Button>
            <p className="text-xs text-ink-soft">You'll chat in Messages. Never pay before you've seen the book.</p>
          </Card>
        )}

        {user && !book.is_mine && (
          <div className="flex gap-3 text-xs">
            <button className="text-ink-soft hover:text-red-700 hover:underline" onClick={() => setReporting(!reporting)}>Report listing</button>
            <button className="text-ink-soft hover:text-red-700 hover:underline" onClick={block}>Block seller</button>
          </div>
        )}
        {reporting && <ReportForm bookId={book.id} onClose={() => setReporting(false)} />}
      </div>
    </div>
  )
}
