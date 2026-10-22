import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { api, rows, getAll } from '../api.js'
import { Banner, Badge } from '../components/Layout.jsx'
import JobForm, { jobToForm } from '../components/JobForm.jsx'
import { useAuth } from '../auth.jsx'

const STATUSES = ['submitted', 'screening', 'interview', 'offer', 'rejected', 'withdrawn']

// Job detail plays two roles:
//  * seeker -> description + apply form (auto-scored on submit)
//  * recruiter (owner) -> ranked candidate list + status dropdowns
export default function JobDetail() {
  const { id } = useParams()
  const { isSeeker, isRecruiter, user } = useAuth()
  const [job, setJob] = useState(null)
  const [resumes, setResumes] = useState([])
  const [applications, setApplications] = useState([])
  const [isOwner, setIsOwner] = useState(false)
  const [resumeId, setResumeId] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState(false)
  const [editForm, setEditForm] = useState(jobToForm(null))

  const load = async () => {
    try {
      const j = await api.get(`/api/jobs/${id}/`)
      setJob(j)
      setIsOwner(j.created_by === user?.id)
      if (isSeeker) {
        const r = await api.get('/api/resumes/')
        const parsed = rows(r).filter((x) => x.parse_status === 'parsed')
        setResumes(parsed)
        if (parsed.length && !resumeId) setResumeId(String(parsed[0].id))
      }
      if (isRecruiter && (user?.id === j.created_by || user?.role === 'admin')) {
        const a = await getAll(`/api/jobs/${id}/applications/`)
        setApplications(rows(a)) // endpoint ranks by ats_score desc
      }
      setError('')
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => {
    load()
  }, [id])

  const apply = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const app = await api.post(`/api/jobs/${id}/apply/`, {
        resume: Number(resumeId),
        message,
      })
      setNotice(
        `Applied! Your resume scored ${app.ats_score}/100 ` +
          `(${(app.matched_skills || []).length} matched skills).`,
      )
      setMessage('')
      await load()
    } catch (err) {
      setError(err.message) // 409 dup/closed, 404 foreign resume, 409 unparsed
    } finally {
      setBusy(false)
    }
  }

  const setStatus = async (appId, status) => {
    try {
      await api.patch(`/api/applications/${appId}/`, { status })
      await load()
    } catch (err) {
      setError(err.message) // seeker trying non-withdraw -> 400
    }
  }

  const saveEdit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await api.patch(`/api/jobs/${id}/`, editForm)
      setNotice('Posting updated.')
      setEditing(false)
      await load()
    } catch (err) {
      setError(err.message) // 400 short requirements, 403 not the owner
    } finally {
      setBusy(false)
    }
  }

  const toggleActive = async () => {
    try {
      await api.patch(`/api/jobs/${id}/`, { is_active: !job.is_active })
      await load()
    } catch (err) {
      setError(err.message)
    }
  }

  if (!job) return <p className="muted">{error || 'Loading…'}</p>

  return (
    <>
      <p><Link to="/jobs">← Back to job board</Link></p>
      <h1>{job.title}</h1>
      <p className="muted">
        {job.company_name || 'Independent'} · {job.location || 'Remote'} ·{' '}
        {job.job_type.replace('_', ' ')} · {job.salary_range || 'Salary TBD'}
      </p>
      <Banner kind="error">{error}</Banner>
      <Banner kind="ok">{notice}</Banner>

      {isRecruiter && isOwner && (
        <div className="card owner-bar">
          <div>
            <strong>You own this posting.</strong>{' '}
            <span className="muted">
              {job.is_active
                ? 'It is open and accepting applications.'
                : 'It is closed — seekers cannot apply.'}
            </span>
          </div>
          <div>
            <button
              className="secondary small"
              onClick={() => {
                setEditForm(jobToForm(job))
                setEditing(!editing)
              }}
            >
              {editing ? 'Cancel edit' : 'Edit posting'}
            </button>{' '}
            <button className="secondary small" onClick={toggleActive}>
              {job.is_active ? 'Close posting' : 'Reopen posting'}
            </button>
          </div>
        </div>
      )}

      {editing && isRecruiter && isOwner && (
        <div className="card">
          <h2>Edit posting</h2>
          <JobForm
            form={editForm}
            onChange={setEditForm}
            onSubmit={saveEdit}
            busy={busy}
            submitLabel="Save changes"
          />
        </div>
      )}

      <div className="grid two">
        <div className="card">
          <h2>About the role</h2>
          <p style={{ whiteSpace: 'pre-wrap' }}>{job.description}</p>
          <h2>Requirements</h2>
          <p className="muted" style={{ whiteSpace: 'pre-wrap' }}>{job.requirements}</p>
        </div>

        {isSeeker && (
          <div className="card">
            <h2>Apply</h2>
            {resumes.length === 0 ? (
              <p className="muted">
                You need a parsed resume first — <Link to="/resumes">upload one</Link>.
              </p>
            ) : (
              <form onSubmit={apply}>
                <label>Resume (must be parsed)</label>
                <select value={resumeId} onChange={(e) => setResumeId(e.target.value)}>
                  {resumes.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.title || r.original_filename}
                    </option>
                  ))}
                </select>
                <label>Cover note (optional)</label>
                <textarea value={message} onChange={(e) => setMessage(e.target.value)} />
                <button disabled={busy}>
                  {busy ? 'Scoring & submitting…' : 'Apply now'}
                </button>
                <p className="muted">
                  On submit your stored parse is scored against the requirements
                  above — instant feedback, 0–100.
                </p>
              </form>
            )}
          </div>
        )}

        {isRecruiter && isOwner && (
          <div className="card">
            <h2>Candidates ({applications.length})</h2>
            <p className="muted">
              Ranked by ATS score — a snapshot, never re-computed.
            </p>
            {applications.length === 0 && <p className="muted">No applications yet.</p>}
            {applications.length > 0 && (
              <table className="list">
                <thead>
                  <tr><th>#</th><th>Candidate</th><th>Score</th><th>Status</th></tr>
                </thead>
                <tbody>
                  {applications.map((a, i) => (
                    <tr key={a.id}>
                      <td>{i + 1}</td>
                      <td>
                        {a.seeker_email}
                        <div className="muted" style={{ fontSize: 12 }}>
                          {(a.matched_skills || []).slice(0, 4).join(', ') ||
                            'no matched skills'}
                        </div>
                      </td>
                      <td>
                        <span className="score" style={{ fontSize: 20 }}>
                          {a.ats_score ?? '—'}
                        </span>
                      </td>
                      <td>
                        <Badge status={a.status} />
                        <select
                          style={{ marginTop: 6 }}
                          value={a.status}
                          onChange={(e) => setStatus(a.id, e.target.value)}
                        >
                          {STATUSES.map((s) => (
                            <option key={s} value={s}>{s}</option>
                          ))}
                        </select>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
    </>
  )
}

