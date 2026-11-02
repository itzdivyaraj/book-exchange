// Home page: search + filters + book grid + pages.
// Filters live in the URL (?q=physics&page=2) so Back/Forward and sharing a link work.
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import BookCard from '../components/BookCard'
import CollegePicker from '../components/CollegePicker'
import { Pagination } from '../components/Extras'
import { Alert, Button, CONDITIONS, Empty, Input, Select, Spinner } from '../components/ui'

const FILTER_KEYS = ['q', 'college_id', 'subject', 'semester', 'condition', 'min_price', 'max_price', 'sort', 'page']

export default function Browse() {
  const { user } = useAuth()
  const [params, setParams] = useSearchParams()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [college, setCollege] = useState(null)
  const [search, setSearch] = useState(params.get('q') || '')
  const [showFilters, setShowFilters] = useState(false)

  // First visit while logged in: show your own college's books.
  useEffect(() => {
    if (user && !params.has('college_id') && !params.has('all')) {
      setParams((p) => { p.set('college_id', user.college.id); return p }, { replace: true })
    }
  }, [user]) // eslint-disable-line react-hooks/exhaustive-deps

  // Keep the college chip in sync with the URL.
  const collegeId = params.get('college_id')
  useEffect(() => {
    if (!collegeId) return setCollege(null)
    if (college?.id === Number(collegeId)) return
    api(`/colleges/${collegeId}`).then(setCollege).catch(() => setCollege(null))
  }, [collegeId]) // eslint-disable-line react-hooks/exhaustive-deps

  // Load books whenever the filters in the URL change.
  useEffect(() => {
    const query = {}
    FILTER_KEYS.forEach((k) => params.get(k) && (query[k] = params.get(k)))
    setError('')
    api('/books', { params: { page_size: 24, ...query } })
      .then(setData)
      .catch((e) => setError(e.message))
  }, [params])

  const update = (changes) =>
    setParams((p) => {
      Object.entries(changes).forEach(([k, v]) => (v === '' || v == null ? p.delete(k) : p.set(k, v)))
      if (!('page' in changes)) p.delete('page') // new filters -> back to page 1
      return p
    })

  const hasFilters = ['subject', 'semester', 'condition', 'min_price', 'max_price'].some((k) => params.get(k))

  return (
    <div>
      <section className="mb-6">
        <h1 className="text-3xl font-bold sm:text-4xl">Textbooks from your campus</h1>
        <p className="mt-1 text-ink-soft">Find last semester's books at student prices. Meet on campus, check the book, then pay.</p>
        <form
          className="mt-4 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            update({ q: search.trim() })
          }}
        >
          <Input type="search" placeholder="Search title, author, subject or ISBN" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search books" />
          <Button type="submit" variant="accent">Search</Button>
        </form>
      </section>

      <div className="mb-4 grid gap-3 rounded-xl border border-line bg-surface p-3 sm:grid-cols-[1fr_auto_auto] sm:items-center">
        <div className="min-w-0">
          <CollegePicker
            value={college}
            allowAdd={false}
            placeholder="All colleges (type to filter by one)"
            onChange={(c) => {
              setCollege(c)
              setParams((p) => {
                c ? p.set('college_id', c.id) : p.delete('college_id')
                c ? p.delete('all') : p.set('all', '1')
                p.delete('page')
                return p
              })
            }}
          />
        </div>
        <Select value={params.get('sort') || 'newest'} onChange={(e) => update({ sort: e.target.value === 'newest' ? '' : e.target.value })} aria-label="Sort">
          <option value="newest">Newest first</option>
          <option value="price_low">Price: low to high</option>
          <option value="price_high">Price: high to low</option>
          <option value="oldest">Oldest first</option>
        </Select>
        <Button variant="secondary" onClick={() => setShowFilters(!showFilters)}>
          Filters{hasFilters ? ' •' : ''}
        </Button>
        {showFilters && (
          <div className="grid gap-2 sm:col-span-3 sm:grid-cols-5">
            <Input placeholder="Subject" defaultValue={params.get('subject') || ''} onBlur={(e) => update({ subject: e.target.value.trim() })} aria-label="Subject" />
            <Select value={params.get('semester') || ''} onChange={(e) => update({ semester: e.target.value })} aria-label="Semester">
              <option value="">Any semester</option>
              {Array.from({ length: 12 }, (_, i) => <option key={i + 1} value={i + 1}>Semester {i + 1}</option>)}
            </Select>
            <Select value={params.get('condition') || ''} onChange={(e) => update({ condition: e.target.value })} aria-label="Condition">
              <option value="">Any condition</option>
              {Object.entries(CONDITIONS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </Select>
            <Input type="number" min="0" placeholder="Min ₹" defaultValue={params.get('min_price') || ''} onBlur={(e) => update({ min_price: e.target.value })} aria-label="Minimum price" />
            <Input type="number" min="0" placeholder="Max ₹" defaultValue={params.get('max_price') || ''} onBlur={(e) => update({ max_price: e.target.value })} aria-label="Maximum price" />
            {hasFilters && (
              <Button variant="ghost" className="sm:col-span-5 sm:justify-self-start" onClick={() => update({ subject: '', semester: '', condition: '', min_price: '', max_price: '' })}>
                Clear filters
              </Button>
            )}
          </div>
        )}
      </div>

      <Alert>{error}</Alert>
      {!data && !error && <Spinner className="mt-12" />}
      {data && (
        <>
          <p className="mb-3 text-sm text-ink-soft">
            {data.total} book{data.total === 1 ? '' : 's'} {college ? `at ${college.name}` : 'across all colleges'}
          </p>
          {data.items.length === 0 ? (
            <Empty title="No books here yet">
              {college ? (
                <>Be the first to list one, or <button className="font-medium text-accent-dark hover:underline" onClick={() => setParams({ all: '1' })}>browse all colleges</button>.</>
              ) : (
                'Try a different search.'
              )}
              {user && <div className="mt-3"><Link to="/sell"><Button variant="accent">Sell a book</Button></Link></div>}
            </Empty>
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
              {data.items.map((b) => <BookCard key={b.id} book={b} />)}
            </div>
          )}
          <Pagination page={data.page} pages={data.pages} onPage={(p) => { update({ page: p }); window.scrollTo(0, 0) }} />
        </>
      )}
    </div>
  )
}
