import { Link } from 'react-router-dom'
import { CONDITIONS, StatusBadge, formatPrice } from './ui'

export function BookCover({ book, className = '' }) {
  const url = book.images?.[0]?.url || book.image_url
  return url ? (
    <img src={url} alt={book.title} className={`object-cover ${className}`} loading="lazy" />
  ) : (
    // No photo: a simple "book spine" placeholder with the title
    <div className={`flex items-center justify-center bg-gradient-to-br from-ink to-[#2f3d5f] p-3 text-center ${className}`}>
      <span className="line-clamp-3 font-display text-sm text-paper/90">{book.title}</span>
    </div>
  )
}

export default function BookCard({ book }) {
  return (
    <Link
      to={`/books/${book.id}`}
      className="group flex flex-col overflow-hidden rounded-xl border border-line bg-white transition hover:-translate-y-0.5 hover:shadow-md"
    >
      <BookCover book={book} className="aspect-[4/3] w-full" />
      <div className="flex flex-1 flex-col gap-1 p-3">
        <div className="flex items-start justify-between gap-2">
          <h3 className="line-clamp-2 font-sans text-sm font-semibold leading-snug group-hover:underline">{book.title}</h3>
          <span className="shrink-0 font-display text-base font-bold text-accent-dark">{formatPrice(book.price)}</span>
        </div>
        <p className="line-clamp-1 text-xs text-ink-soft">{book.author}</p>
        <div className="mt-auto flex flex-wrap items-center gap-1.5 pt-2 text-xs text-ink-soft">
          <span className="rounded bg-paper px-1.5 py-0.5">{CONDITIONS[book.condition]}</span>
          {book.semester && <span className="rounded bg-paper px-1.5 py-0.5">Sem {book.semester}</span>}
          {book.status !== 'available' && <StatusBadge status={book.status} />}
        </div>
        <p className="line-clamp-1 text-xs text-ink-soft">{book.college.name}</p>
      </div>
    </Link>
  )
}
