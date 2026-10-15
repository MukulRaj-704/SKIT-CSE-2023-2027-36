import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { useAuth } from '../auth.jsx'
import { Banner } from '../components/Layout.jsx'

// One screen for both /login and /register (mode prop switches the form).
export default function AuthPage({ mode }) {
  const { login, register } = useAuth()
  const navigate = useNavigate()
  const isRegister = mode === 'register'

  const [form, setForm] = useState({
    email: '',
    password: '',
    first_name: '',
    last_name: '',
    role: 'job_seeker',
    company_name: '',
  })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value })

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      if (isRegister) {
        const payload = {
          email: form.email,
          first_name: form.first_name,
          last_name: form.last_name,
          password: form.password,
          password_confirm: form.password,
          role: form.role,
        }
        if (form.role === 'recruiter') payload.company_name = form.company_name
        await register(payload)
      } else {
        await login(form.email, form.password)
      }
      navigate('/')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth-box">
      <div className="card">
        <h1>{isRegister ? 'Create your account' : 'Sign in to JobRix'}</h1>
        <Banner kind="error">{error}</Banner>

        <form onSubmit={submit}>
          {isRegister && (
            <>
              <div className="grid two">
                <div>
                  <label>First name</label>
                  <input value={form.first_name} onChange={set('first_name')} required />
                </div>
                <div>
                  <label>Last name</label>
                  <input value={form.last_name} onChange={set('last_name')} required />
                </div>
              </div>
              <label>I am a</label>
              <select value={form.role} onChange={set('role')}>
                <option value="job_seeker">Job seeker</option>
                <option value="recruiter">Recruiter</option>
              </select>
              {form.role === 'recruiter' && (
                <>
                  <label>Company name</label>
                  <input
                    value={form.company_name}
                    onChange={set('company_name')}
                    placeholder="Acme Corp"
                    required
                  />
                </>
              )}
            </>
          )}

          <label>Email</label>
          <input type="email" value={form.email} onChange={set('email')} required />

          <label>Password</label>
          <input
            type="password"
            value={form.password}
            onChange={set('password')}
            required
            minLength={8}
          />

          <button disabled={busy}>
            {busy ? 'Working…' : isRegister ? 'Create account' : 'Sign in'}
          </button>
        </form>

        <p className="switch">
          {isRegister ? (
            <>
              Already registered? <Link to="/login">Sign in</Link>
            </>
          ) : (
            <>
              New here? <Link to="/register">Create an account</Link>
            </>
          )}
        </p>
      </div>
    </div>
  )
}
