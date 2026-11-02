// Which page shows for which address.
import { Link, Route, Routes } from 'react-router-dom'
import { RequireAuth } from './auth'
import Layout from './components/Layout'
import { Empty } from './components/ui'
import Account from './pages/Account'
import { ForgotPassword, Login, ResetPassword, Signup, VerifyEmail } from './pages/AuthPages'
import BookDetail from './pages/BookDetail'
import BookForm from './pages/BookForm'
import Browse from './pages/Browse'
import { Chat, Inbox } from './pages/Messages'
import MyListings from './pages/MyListings'

const loggedIn = (page) => <RequireAuth>{page}</RequireAuth>

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        {/* Anyone */}
        <Route path="/" element={<Browse />} />
        <Route path="/books/:id" element={<BookDetail />} />
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />
        <Route path="/verify" element={<VerifyEmail />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        {/* Logged in only */}
        <Route path="/sell" element={loggedIn(<BookForm />)} />
        <Route path="/books/:id/edit" element={loggedIn(<BookForm />)} />
        <Route path="/my-listings" element={loggedIn(<MyListings />)} />
        <Route path="/messages" element={loggedIn(<Inbox />)} />
        <Route path="/messages/:id" element={loggedIn(<Chat />)} />
        <Route path="/account" element={loggedIn(<Account />)} />
        <Route path="*" element={<Empty title="Page not found"><Link to="/" className="font-medium text-accent-dark hover:underline">Back to books</Link></Empty>} />
      </Route>
    </Routes>
  )
}
