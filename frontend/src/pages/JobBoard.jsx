import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { api, rows } from '../api.js'
import { Banner } from '../components/Layout.jsx'

// The job board: every signed-in member can browse open postings.
export default function JobBoard() {
  const [jobs, setJobs] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    api
      .get('/api/jobs/')
      .then((data) => setJobs(rows(data)))
      .catch((err) => setError(err.message))
  }, [])

  return (
    <>
      <h1>Job board</h1>
      <Banner kind="error">{error}</Banner>
      <p className="muted">
        Open postings only — closed jobs disappear from this list (their
        applications keep working).
      </p>

      <div className="card">
        {jobs.length === 0 && !error && <p className="muted">No open jobs yet.</p>}
        {jobs.length > 0 && (
          <table className="list">
            <thead>
              <tr>
                <th>Title</th><th>Company</th><th>Location</th><th>Type</th><th>Salary</th><th></th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.id}>
                  <td>
                    <Link to={`/jobs/${job.id}`}>{job.title}</Link>
                  </td>
                  <td>{job.company_name || '—'}</td>
                  <td>{job.location || '—'}</td>
                  <td>{job.job_type.replace('_', ' ')}</td>
                  <td>{job.salary_range || '—'}</td>
                  <td>
                    <Link className="btn" style={{ padding: '5px 10px', marginTop: 0, fontSize: 13 }} to={`/jobs/${job.id}`}>
                      View / apply
                    </Link>
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
