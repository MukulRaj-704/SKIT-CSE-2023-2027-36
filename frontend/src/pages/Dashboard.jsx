import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { getAll } from '../api.js'
import { useAuth } from '../auth.jsx'

// Role-aware landing page: the counts a mentor cares about + where to go next.
export default function Dashboard() {
  const { user, isSeeker, isRecruiter } = useAuth()
  const [stats, setStats] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        if (isSeeker) {
          const [resumes, jobs, applications] = await Promise.all([
            getAll('/api/resumes/'),
            getAll('/api/jobs/'),
            getAll('/api/applications/'),
          ])
          if (!cancelled)
            setStats({
              resumes: resumes.count,
              jobs: jobs.count,
              applications: applications.count,
            })
        } else if (isRecruiter) {
          const [jobs, seekers] = await Promise.all([
            getAll('/api/jobs/'),
            // Recruiters may browse candidates; a platform admin has none to
            // list, so that one call is allowed to fail silently.
            getAll('/api/accounts/seekers/').catch(() => ({ count: '—' })),
          ])
          if (!cancelled) setStats({ jobs: jobs.count, seekers: seekers.count })
        }
      } catch (err) {
        if (!cancelled) setError(err.message)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [isSeeker, isRecruiter])

  return (
    <>
      <h1>
        Welcome back, {user?.first_name || user?.email}
      </h1>
      <p className="muted">
        JobRix ties the three apps together: parse a resume once, score it against
        jobs, and move applications through the pipeline.
      </p>

      {error && <div className="error">{error}</div>}

      <div className="grid three">
        {isSeeker && stats && (
          <>
            <Link className="tile" to="/resumes">
              <div className="n">{stats.resumes}</div>
              <div className="l">Resumes (parsed once, reused everywhere)</div>
            </Link>
            <Link className="tile" to="/jobs">
              <div className="n">{stats.jobs}</div>
              <div className="l">Open jobs you can apply to</div>
            </Link>
            <Link className="tile" to="/applications">
              <div className="n">{stats.applications}</div>
              <div className="l">Your applications</div>
            </Link>
          </>
        )}
        {isRecruiter && stats && (
          <>
            <Link className="tile" to="/postings">
              <div className="n">{stats.jobs}</div>
              <div className="l">Your postings</div>
            </Link>
            <Link className="tile" to="/postings">
              <div className="n">{stats.seekers}</div>
              <div className="l">Job seekers on the platform</div>
            </Link>
          </>
        )}
      </div>

      <div className="card" style={{ marginTop: 20 }}>
        <h2>How the demo flows</h2>
        {isSeeker ? (
          <ol className="muted">
            <li>Upload a PDF resume — it is parsed <b>once</b> and stored as JSON.</li>
            <li>Browse the job board and apply — your resume is scored against the posting (0–100) with matched/missing skills.</li>
            <li>Track each application: submitted → screening → interview → offer.</li>
          </ol>
        ) : (
          <ol className="muted">
            <li>Post a job — the <b>requirements</b> double as the ATS scoring text.</li>
            <li>Open a posting to see candidates <b>ranked by ATS score</b>.</li>
            <li>Move applicants through the pipeline with the status dropdown.</li>
          </ol>
        )}
      </div>
    </>
  )
}
