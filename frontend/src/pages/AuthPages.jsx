// Log in, sign up, verify email, forgot password, reset password.
import { useEffect, useState } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import CollegePicker from '../components/CollegePicker'
import { Alert, Button, Card, Field, Input } from '../components/ui'

function AuthShell({ title, subtitle, children, footer }) {
  return (
    <div className="mx-auto mt-6 max-w-md">
      <h1 className="text-3xl font-bold">{title}</h1>
      {subtitle && <p className="mt-1 text-sm text-ink-soft">{subtitle}</p>}
      <Card className="mt-5">{children}</Card>
      {footer && <div className="mt-4 text-center text-sm text-ink-soft">{footer}</div>}
    </div>
  )
}

const link = 'font-medium text-accent-dark hover:underline'

export function Login() {
  const { user, signIn } = useAuth()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [form, setForm] = useState({ email: params.get('email') || '', password: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const next = params.get('next') || '/'

  if (user) return <Navigate to={next} replace />

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const r = await api('/auth/login', { method: 'POST', body: form })
      signIn(r.token, r.user)
      navigate(next, { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthShell title="Welcome back" footer={<>New here? <Link className={link} to="/signup">Create an account</Link></>}>
      {params.get('reset') && <Alert kind="success" className="mb-4">Password changed. Log in with your new password.</Alert>}
      <form onSubmit={submit} className="space-y-4">
        <Field label="Email"><Input type="email" required autoComplete="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
        <Field label="Password"><Input type="password" required autoComplete="current-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></Field>
        <Alert>{error}</Alert>
        <Button type="submit" loading={busy} className="w-full">Log in</Button>
        <p className="text-center text-sm"><Link className={link} to="/forgot-password">Forgot password?</Link></p>
      </form>
    </AuthShell>
  )
}

export function Signup() {
  const { user, signIn } = useAuth()
  const [form, setForm] = useState({ name: '', email: '', password: '' })
  const [college, setCollege] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  // Logged in (including right after signing up): new accounts go to "enter your code".
  if (user) return <Navigate to={user.email_verified ? '/' : '/verify'} replace />

  const submit = async (e) => {
    e.preventDefault()
    if (!college) return setError('Please pick your college.')
    setBusy(true)
    setError('')
    try {
      const r = await api('/auth/signup', { method: 'POST', body: { ...form, college_id: college.id } })
      signIn(r.token, r.user) // the line above then redirects to /verify
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthShell
      title="Join Book Exchange"
      subtitle="Buy and sell used textbooks with students at your college."
      footer={<>Already have an account? <Link className={link} to="/login">Log in</Link></>}
    >
      <form onSubmit={submit} className="space-y-4">
        <Field label="Your name"><Input required minLength={2} maxLength={80} autoComplete="name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
        <Field label="Email" hint="We'll send a 6-digit code to verify it."><Input type="email" required autoComplete="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
        <Field label="Password" hint="At least 8 characters."><Input type="password" required minLength={8} maxLength={72} autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></Field>
        <div>
          <span className="mb-1 block text-sm font-medium">College</span>
          <CollegePicker value={college} onChange={setCollege} />
        </div>
        <Alert>{error}</Alert>
        <Button type="submit" loading={busy} className="w-full">Create account</Button>
      </form>
    </AuthShell>
  )
}

export function VerifyEmail() {
  const { user, setUser } = useAuth()
  const navigate = useNavigate()
  const [code, setCode] = useState('')
  const [msg, setMsg] = useState({ kind: 'error', text: '' })
  const [busy, setBusy] = useState(false)
  const [cooldown, setCooldown] = useState(0)

  useEffect(() => {
    if (cooldown <= 0) return
    const t = setTimeout(() => setCooldown(cooldown - 1), 1000)
    return () => clearTimeout(t)
  }, [cooldown])

  if (!user) return <Navigate to="/login?next=/verify" replace />
  if (user.email_verified) return <Navigate to="/" replace />

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setMsg({ kind: 'error', text: '' })
    try {
      setUser(await api('/auth/verify-email', { method: 'POST', body: { code } }))
      navigate('/', { replace: true })
    } catch (err) {
      setMsg({ kind: 'error', text: err.message })
    } finally {
      setBusy(false)
    }
  }

  const resend = async () => {
    try {
      const r = await api('/auth/resend-verification', { method: 'POST' })
      setMsg({ kind: 'success', text: r.detail })
      setCooldown(60)
    } catch (err) {
      setMsg({ kind: 'error', text: err.message })
    }
  }

  return (
    <AuthShell title="Check your email" subtitle={`We sent a 6-digit code to ${user.email}. It expires in 15 minutes.`}>
      <form onSubmit={submit} className="space-y-4">
        <Field label="Verification code">
          <Input
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            pattern="\d{6}"
            required
            placeholder="123456"
            className="w-full rounded-lg border border-line bg-surface px-3 py-3 text-center font-mono text-2xl tracking-[0.5em]"
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
          />
        </Field>
        <Alert kind={msg.kind}>{msg.text}</Alert>
        <Button type="submit" loading={busy} disabled={code.length !== 6} className="w-full">Verify</Button>
        <p className="text-center text-sm text-ink-soft">
          Didn't get it? Check spam, or{' '}
          <button type="button" className={link} disabled={cooldown > 0} onClick={resend}>
            {cooldown > 0 ? `resend in ${cooldown}s` : 'send a new code'}
          </button>
        </p>
      </form>
    </AuthShell>
  )
}

export function ForgotPassword() {
  const [email, setEmail] = useState('')
  const [done, setDone] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      setDone((await api('/auth/forgot-password', { method: 'POST', body: { email } })).detail)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthShell title="Forgot your password?" subtitle="Enter your email and we'll send you a reset code.">
      {done ? (
        <div className="space-y-4">
          <Alert kind="success">{done}</Alert>
          <Link to={`/reset-password?email=${encodeURIComponent(email)}`}>
            <Button className="w-full">I have the code</Button>
          </Link>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <Field label="Email"><Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
          <Alert>{error}</Alert>
          <Button type="submit" loading={busy} className="w-full">Send reset code</Button>
        </form>
      )}
    </AuthShell>
  )
}

export function ResetPassword() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [form, setForm] = useState({ email: params.get('email') || '', code: '', new_password: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await api('/auth/reset-password', { method: 'POST', body: form })
      navigate(`/login?reset=1&email=${encodeURIComponent(form.email)}`, { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthShell title="Set a new password" subtitle="This will log you out on every device.">
      <form onSubmit={submit} className="space-y-4">
        <Field label="Email"><Input type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
        <Field label="6-digit code"><Input inputMode="numeric" maxLength={6} required value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.replace(/\D/g, '') })} /></Field>
        <Field label="New password" hint="At least 8 characters."><Input type="password" minLength={8} maxLength={72} required autoComplete="new-password" value={form.new_password} onChange={(e) => setForm({ ...form, new_password: e.target.value })} /></Field>
        <Alert>{error}</Alert>
        <Button type="submit" loading={busy} className="w-full">Change password</Button>
      </form>
    </AuthShell>
  )
}
