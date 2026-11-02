// The frame around every page: top bar, "verify your email" banner, footer.
import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'

function useUnreadCount(user) {
  const [count, setCount] = useState(0)
  const location = useLocation()
  useEffect(() => {
    if (!user) return setCount(0)
    let stop = false
    const load = () =>
      api('/requests')
        .then((rows) => !stop && setCount(rows.reduce((n, r) => n + r.unread_count, 0)))
        .catch(() => {})
    load()
    const timer = setInterval(load, 30000) // check every 30 seconds
    return () => {
      stop = true
      clearInterval(timer)
    }
  }, [user, location.pathname]) // also re-check when you move between pages
  return count
}

const navClass = ({ isActive }) =>
  `rounded-lg px-3 py-1.5 text-sm font-medium transition ${isActive ? 'bg-ink text-paper' : 'text-ink-soft hover:bg-black/5 hover:text-ink'}`

export default function Layout() {
  const { user, signOut } = useAuth()
  const unread = useUnreadCount(user)
  const navigate = useNavigate()

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-20 border-b border-line bg-paper/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-2 px-4 py-3">
          <Link to="/" className="mr-2 flex items-center gap-2">
            <img src="/favicon.svg" alt="" className="h-7 w-7" />
            <span className="font-display text-lg font-bold">Book Exchange</span>
          </Link>
          <nav className="flex flex-1 flex-wrap items-center gap-1">
            <NavLink to="/" end className={navClass}>Browse</NavLink>
            {user && (
              <>
                <NavLink to="/sell" className={navClass}>Sell a book</NavLink>
                <NavLink to="/my-listings" className={navClass}>My listings</NavLink>
                <NavLink to="/messages" className={navClass}>
                  Messages
                  {unread > 0 && (
                    <span className="ml-1.5 rounded-full bg-accent px-1.5 py-0.5 text-xs text-white" aria-label={`${unread} unread`}>
                      {unread}
                    </span>
                  )}
                </NavLink>
              </>
            )}
          </nav>
          <div className="flex items-center gap-1">
            {user ? (
              <>
                <NavLink to="/account" className={navClass}>{user.name.split(' ')[0]}</NavLink>
                <button
                  onClick={async () => {
                    await signOut()
                    navigate('/')
                  }}
                  className="rounded-lg px-3 py-1.5 text-sm text-ink-soft hover:bg-black/5 hover:text-ink"
                >
                  Log out
                </button>
              </>
            ) : (
              <>
                <NavLink to="/login" className={navClass}>Log in</NavLink>
                <Link to="/signup" className="rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-white hover:bg-accent-dark">
                  Sign up
                </Link>
              </>
            )}
          </div>
        </div>
        {user && !user.email_verified && (
          <div className="border-t border-amber-200 bg-amber-50 px-4 py-2 text-center text-sm text-amber-900">
            Verify your email to list books and message sellers.{' '}
            <Link to="/verify" className="font-semibold underline">Enter your code</Link>
          </div>
        )}
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
        <Outlet />
      </main>

      <footer className="border-t border-line px-4 py-6 text-center text-xs text-ink-soft">
        Meet in a public place on campus. Never pay before you've seen the book.
      </footer>
    </div>
  )
}
