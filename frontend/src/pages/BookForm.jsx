// "Sell a book" (new) and "Edit listing" (existing, + photos).
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { Alert, Button, CONDITIONS, Card, Field, Input, Select, Spinner, Textarea } from '../components/ui'

const EMPTY = { title: '', author: '', edition: '', isbn: '', subject: '', semester: '', condition: 'good', price: '', description: '' }

export default function BookForm() {
  const { id } = useParams()
  const isEdit = !!id
  const { user } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [form, setForm] = useState(EMPTY)
  const [book, setBook] = useState(null)
  const [loading, setLoading] = useState(isEdit)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState('')
  const [busy, setBusy] = useState(false)
  const [duplicate, setDuplicate] = useState('')

  useEffect(() => {
    if (!isEdit) return
    api(`/books/${id}`)
      .then((b) => {
        if (!b.is_mine) return navigate(`/books/${id}`, { replace: true })
        setBook(b)
        setForm(Object.fromEntries(Object.keys(EMPTY).map((k) => [k, b[k] ?? ''])))
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [id]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!user.email_verified)
    return <Alert kind="info">Verify your email before listing books. <Link to="/verify" className="font-semibold underline">Enter your code</Link></Alert>
  if (loading) return <Spinner className="mt-24" />

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  const payload = () => {
    const p = { ...form, price: Number(form.price), semester: form.semester ? Number(form.semester) : null }
    ;['edition', 'isbn', 'subject', 'description'].forEach((k) => (p[k] = p[k]?.trim() || null))
    return p
  }

  const submit = async (e, allowDuplicate = false) => {
    e?.preventDefault()
    setBusy(true)
    setError('')
    setSaved('')
    try {
      if (isEdit) {
        setBook(await api(`/books/${id}`, { method: 'PATCH', body: payload() }))
        setSaved('Saved.')
      } else {
        const b = await api('/books', { method: 'POST', body: { ...payload(), allow_duplicate: allowDuplicate } })
        navigate(`/books/${b.id}/edit?new=1`, { replace: true }) // next: add photos
      }
    } catch (err) {
      // 409 on create = "you already listed this". Ask before listing a second copy.
      if (!isEdit && err.status === 409 && err.message.includes('already have this book')) setDuplicate(err.message)
      else setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-3xl font-bold">{isEdit ? 'Edit listing' : 'Sell a book'}</h1>
      {params.get('new') && <Alert kind="success" className="mt-3">Your book is listed! Add up to 3 photos below. Listings with photos get more requests.</Alert>}

      {isEdit && book && <Photos book={book} onChange={setBook} />}

      <Card className="mt-5">
        <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2"><Field label="Title *"><Input required minLength={2} maxLength={200} value={form.title} onChange={set('title')} placeholder="Concepts of Physics Vol 1" /></Field></div>
          <Field label="Author *"><Input required minLength={2} maxLength={150} value={form.author} onChange={set('author')} placeholder="H C Verma" /></Field>
          <Field label="Price (₹) *" hint="0 = giving it away free"><Input required type="number" min="0" max="100000" value={form.price} onChange={set('price')} /></Field>
          <Field label="Condition">
            <Select value={form.condition} onChange={set('condition')}>
              {Object.entries(CONDITIONS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </Select>
          </Field>
          <Field label="Semester">
            <Select value={form.semester} onChange={set('semester')}>
              <option value="">Not specific</option>
              {Array.from({ length: 12 }, (_, i) => <option key={i + 1} value={i + 1}>Semester {i + 1}</option>)}
            </Select>
          </Field>
          <Field label="Subject"><Input maxLength={100} value={form.subject} onChange={set('subject')} placeholder="Physics" /></Field>
          <Field label="Edition"><Input maxLength={50} value={form.edition} onChange={set('edition')} placeholder="2022" /></Field>
          <div className="sm:col-span-2"><Field label="ISBN"><Input maxLength={20} value={form.isbn} onChange={set('isbn')} /></Field></div>
          <div className="sm:col-span-2"><Field label="Description" hint="Highlighting, missing pages, where you can meet…"><Textarea maxLength={1000} value={form.description} onChange={set('description')} /></Field></div>

          <div className="space-y-2 sm:col-span-2">
            <Alert>{error}</Alert>
            <Alert kind="success">{saved}</Alert>
            {duplicate ? (
              <Alert kind="info">
                <p>{duplicate.split('(')[0].trim()}.</p>
                <div className="mt-2 flex gap-2">
                  <Button type="button" variant="secondary" loading={busy} onClick={() => submit(null, true)}>Yes, list a second copy</Button>
                  <Link to="/my-listings"><Button type="button" variant="ghost">See my listings</Button></Link>
                </div>
              </Alert>
            ) : (
              <Button type="submit" loading={busy} variant="accent">{isEdit ? 'Save changes' : 'List book'}</Button>
            )}
          </div>
        </form>
      </Card>
    </div>
  )
}

function Photos({ book, onChange }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const fileInput = useRef()

  const upload = async (file) => {
    if (!file) return
    setBusy(true)
    setError('')
    const form = new FormData()
    form.append('file', file)
    try {
      onChange(await api(`/books/${book.id}/images`, { method: 'POST', form }))
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
      fileInput.current.value = ''
    }
  }

  const remove = async (imageId) => {
    try {
      onChange(await api(`/books/${book.id}/images/${imageId}`, { method: 'DELETE' }))
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <Card className="mt-5">
      <p className="font-medium">Photos <span className="text-sm font-normal text-ink-soft">({book.images.length}/3)</span></p>
      <p className="text-xs text-ink-soft">JPG, PNG or WEBP, up to 5 MB. Location data is removed automatically.</p>
      <div className="mt-3 flex flex-wrap gap-3">
        {book.images.map((img) => (
          <div key={img.id} className="relative">
            <img src={img.url} alt="" className="h-28 w-36 rounded-lg border border-line object-cover" />
            <button onClick={() => remove(img.id)} className="absolute right-1 top-1 rounded-full bg-white/90 px-2 text-xs font-medium text-red-700 shadow" aria-label="Remove photo">
              Remove
            </button>
          </div>
        ))}
        {book.images.length < 3 && (
          <label className="flex h-28 w-36 cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-line text-sm text-ink-soft hover:border-ink/40">
            {busy ? 'Uploading…' : '+ Add photo'}
            <input ref={fileInput} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" disabled={busy} onChange={(e) => upload(e.target.files[0])} />
          </label>
        )}
      </div>
      <Alert className="mt-2">{error}</Alert>
      <Link to={`/books/${book.id}`} className="mt-3 inline-block text-sm font-medium text-accent-dark hover:underline">View listing →</Link>
    </Card>
  )
}
