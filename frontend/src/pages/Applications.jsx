import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { api, rows, getAll } from '../api.js'
import { Banner, Badge } from '../components/Layout.jsx'

// Seeker's application tracker: status per job + withdraw action.
export default function Applications() {
  const [list, setList] = useState([])
  const [error, setError] = useState('')

  const load = async () => {
    try {
      setList(rows(await getAll('/api/applications/')))
      setError('')
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const withdraw = async (app) => {
    try {
      // The API only lets the seeker move their own application to "withdrawn".
      await api.patch(`/api/applications/${app.id}/`, { status: 'withdrawn' })
      await load()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <>
      <h1>My applications</h1>
      <Banner kind="error">{error}</Banner>
      <p className="muted">
        Status is advanced by recruiters; you can withdraw at any time.
      </p>

      <div className="card">
        {list.length === 0 && !error && (
          <p className="muted">
            No applications yet — head to the <Link to="/jobs">job board</Link>.
          </p>
        )}
        {list.length > 0 && (
          <table className="list">
            <thead>
              <tr>
                <th>Job</th><th>Company</th><th>Your score</th><th>Status</th><th>Applied</th><th></th>
              </tr>
            </thead>
            <tbody>
              {list.map((a) => (
                <tr key={a.id}>
                  <td><Link to={`/jobs/${a.job}`}>{a.job_title}</Link></td>
                  <td>{a.job_company || '—'}</td>
                  <td>
                    <span className="score" style={{ fontSize: 18 }}>{a.ats_score ?? '—'}</span>
                  </td>
                  <td><Badge status={a.status} /></td>
                  <td className="muted">{new Date(a.created_at).toLocaleDateString()}</td>
                  <td>
                    {['submitted', 'screening', 'interview'].includes(a.status) && (
                      <button className="secondary small" onClick={() => withdraw(a)}>
                        Withdraw
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  )
}
