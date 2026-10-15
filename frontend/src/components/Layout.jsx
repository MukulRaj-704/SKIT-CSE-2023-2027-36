import { NavLink, Outlet } from 'react-router-dom'

import { useAuth } from '../auth.jsx'

// Top bar + routed page content.
export default function Layout() {
  const { user, isSeeker, isRecruiter, logout } = useAuth()
  const roleLabel = user?.role?.replace('_', ' ')

  return (
    <>
      <nav className="nav">
        <NavLink to="/" className="brand">
          JobRix
        </NavLink>
        <NavLink to="/jobs" className="link">
          Jobs
        </NavLink>
        {isSeeker && (
          <>
            <NavLink to="/resumes" className="link">
              My resumes
            </NavLink>
            <NavLink to="/applications" className="link">
              My applications
            </NavLink>
          </>
        )}
        {isRecruiter && <NavLink to="/postings" className="link">My postings</NavLink>}
        <span className="spacer" />
        <span className="who">
          {user?.email} · {roleLabel}
        </span>
        <button className="secondary small" onClick={logout}>
          Sign out
        </button>
      </nav>
      <main className="page">
        <Outlet />
      </main>
    </>
  )
}

// Small status pill shared by resumes and applications.
export function Badge({ status }) {
  const map = {
    parsed: 'ok',
    pending: 'warn',
    failed: 'bad',
    active: 'ok',
    submitted: 'neutral',
    screening: 'warn',
    interview: 'warn',
    offer: 'ok',
    rejected: 'bad',
    withdrawn: 'neutral',
  }
  return <span className={`badge ${map[status] || 'neutral'}`}>{status}</span>
}

// Inline error/success banners.
export function Banner({ kind, children }) {
  if (!children) return null
  return <div className={kind === 'ok' ? 'success' : 'error'}>{children}</div>
}
