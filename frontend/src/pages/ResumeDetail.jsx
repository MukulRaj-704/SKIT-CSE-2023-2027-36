import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { api } from '../api.js'
import { Banner, Badge } from '../components/Layout.jsx'

// One resume: parsed summary, skills, reparse + ad-hoc ATS scoring history.
export default function ResumeDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [resume, setResume] = useState(null)
  const [analyses, setAnalyses] = useState([])
  const [jd, setJd] = useState('')
  const [jobTitle, setJobTitle] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  const load = async () => {
    try {
      const [r, a] = await Promise.all([
        api.get(`/api/resumes/${id}/`),
        api.get(`/api/resumes/${id}/ats/`),
      ])
      setResume(r)
      setAnalyses(a.results || a)
      setError('')
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => {
    load()
  }, [id])

  const reparse = async () => {
    setBusy(true)
    setNotice('')
    try {
      await api.post(`/api/resumes/${id}/reparse/`)
      setNotice('Re-parsed from the stored file.')
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const score = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const result = await api.post(`/api/resumes/${id}/ats/`, {
        job_description: jd,
        job_title: jobTitle,
      })
      setNotice(`Scored ${result.score}/100 — stored in your ATS history.`)
      setJd('')
      setJobTitle('')
      await load()
    } catch (err) {
      setError(err.message) // 409 not parsed / 503 engine down arrive here
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    if (!window.confirm('Delete this resume and its stored file?')) return
    try {
      await api.delete(`/api/resumes/${id}/`)
      navigate('/resumes')
    } catch (err) {
      setError(err.message)
    }
  }

  if (!resume) return <p className="muted">{error || 'Loading…'}</p>

  return (
    <>
      <p>
        <Link to="/resumes">← Back to resumes</Link>
      </p>
      <h1>{resume.title || resume.original_filename}</h1>
      <Banner kind="error">{error}</Banner>
      <Banner kind="ok">{notice}</Banner>

      <div className="grid two">
        <div className="card">
          <h2>
            Parse <Badge status={resume.parse_status} />
          </h2>
          <p className="muted">
            {resume.parse_status === 'parsed'
              ? `Parsed ${new Date(resume.parsed_at).toLocaleString()} — stored as JSON, reused by every score.`
              : resume.parse_error || 'Not parsed yet.'}
          </p>
          <table className="list">
            <tbody>
              <tr><th>Name</th><td>{resume.parsed_summary?.name || '—'}</td></tr>
              <tr><th>Email</th><td>{resume.parsed_summary?.email || '—'}</td></tr>
              <tr><th>Experience</th><td>{resume.parsed_summary?.experience_count ?? '—'} entries</td></tr>
              <tr><th>Education</th><td>{resume.parsed_summary?.education_count ?? '—'} entries</td></tr>
              <tr><th>Size</th><td>{resume.file_size ? `${(resume.file_size / 1024).toFixed(1)} KB` : '—'}</td></tr>
            </tbody>
          </table>
          <div>
            {(resume.skills || []).map((s) => (
              <span className="chip" key={s}>{s}</span>
            ))}
          </div>
          <button className="secondary" onClick={reparse} disabled={busy}>
            Re-parse stored file
          </button>
          <button className="danger" onClick={remove} disabled={busy}>
            Delete resume
          </button>
        </div>

        <div className="card">
          <h2>Run ATS analysis</h2>
          <p className="muted">
            Scores this resume against a job description (engine runs server-side,
            the PDF is not touched).
          </p>
          <form onSubmit={score}>
            <label>Job title (optional)</label>
            <input value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} />
            <label>Job description (min 30 characters)</label>
            <textarea
              value={jd}
              onChange={(e) => setJd(e.target.value)}
              placeholder={'Requirements: Python, Django, Redis, Kubernetes…'}
              required
              minLength={30}
            />
            <button disabled={busy || resume.parse_status !== 'parsed'}>
              {busy ? 'Scoring…' : 'Score it'}
            </button>
            {resume.parse_status !== 'parsed' && (
              <p className="muted">Unavailable until the resume parses successfully.</p>
            )}
          </form>
        </div>
      </div>

      <div className="card">
        <h2>ATS history ({analyses.length})</h2>
        {analyses.length === 0 && <p className="muted">No analyses yet.</p>}
        {analyses.length > 0 && (
          <table className="list">
            <thead>
              <tr>
                <th>Score</th><th>Job</th><th>Matched</th><th>Missing</th><th>When</th>
              </tr>
            </thead>
            <tbody>
              {analyses.map((a) => (
                <tr key={a.id}>
                  <td><span className="score" style={{ fontSize: 18 }}>{a.score}</span></td>
                  <td>{a.job_title || '—'}</td>
                  <td>{(a.matched_skills || []).map((s) => <span className="chip" key={s}>{s}</span>)}</td>
                  <td>{(a.missing_skills || []).map((s) => <span className="chip" key={s}>{s}</span>)}</td>
                  <td className="muted">{new Date(a.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  )
}
