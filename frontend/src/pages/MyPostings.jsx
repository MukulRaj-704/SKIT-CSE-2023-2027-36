import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { api, rows } from '../api.js'
import { Banner, Badge } from '../components/Layout.jsx'

// Recruiter home: create a posting (requirements = ATS scoring text) and
// close/reopen own jobs.
export default function MyPostings() {
  const [jobs, setJobs] = useState([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [form, setForm] = useState({
    title: '',
    location: '',
    job_type: 'full_time',
    salary_range: '',
    description: '',
    requirements: '',
  })

  const load = async () => {
    try {
      setJobs(rows(await api.get('/api/jobs/'))) // recruiter sees own, incl. closed
      setError('')
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value })

  const create = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const job = await api.post('/api/jobs/', form)
      setNotice(`Posted "${job.title}" (company: ${job.company_name || '—'}).`)
      setForm({ ...form, title: '', description: '', requirements: '' })
      await load()
    } catch (err) {
      setError(err.message) // e.g. 400 requirements < 30 chars
    } finally {
      setBusy(false)
    }
  }

  const toggleActive = async (job) => {
    try {
      await api.patch(`/api/jobs/${job.id}/`, { is_active: !job.is_active })
      await load()
    } catch (err) {
      setError(err.message)
    }
  }

  const remove = async (job) => {
    if (!window.confirm(`Delete "${job.title}"? Its applications go too.`)) return
    try {
      await api.delete(`/api/jobs/${job.id}/`)
      await load()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <>
      <h1>My postings</h1>
      <Banner kind="error">{error}</Banner>
      <Banner kind="ok">{notice}</Banner>

      <div className="grid two">
        <div className="card">
          <h2>Post a new job</h2>
          <form onSubmit={create}>
            <label>Title</label>
            <input value={form.title} onChange={set('title')} required />
            <div className="grid two">
              <div>
                <label>Location</label>
                <input value={form.location} onChange={set('location')} />
              </div>
              <div>
                <label>Type</label>
                <select value={form.job_type} onChange={set('job_type')}>
                  <option value="full_time">Full time</option>
                  <option value="part_time">Part time</option>
                  <option value="contract">Contract</option>
                  <option value="internship">Internship</option>
                </select>
              </div>
            </div>
            <label>Salary range</label>
            <input
              value={form.salary_range}
              onChange={set('salary_range')}
              placeholder="INR 12-18 LPA"
            />
            <label>Description</label>
            <textarea value={form.description} onChange={set('description')} required />
            <label>Requirements (min 30 chars — used for ATS scoring)</label>
            <textarea
              value={form.requirements}
              onChange={set('requirements')}
              placeholder={'Requirements: Python, Django, PostgreSQL…'}
              required
              minLength={30}
            />
            <button disabled={busy}>{busy ? 'Posting…' : 'Publish job'}</button>
          </form>
        </div>

        <div className="card">
          <h2>{jobs.length} posting{jobs.length === 1 ? '' : 's'}</h2>
          {jobs.length === 0 && <p className="muted">Nothing posted yet.</p>}
          {jobs.length > 0 && (
            <table className="list">
              <thead>
                <tr><th>Title</th><th>State</th><th>Candidates</th><th></th></tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr key={job.id}>
                    <td><Link to={`/jobs/${job.id}`}>{job.title}</Link></td>
                    <td>
                      <Badge status={job.is_active ? 'active' : 'rejected'} />
                    </td>
                    <td>{job.applications_count}</td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <button className="secondary small" onClick={() => toggleActive(job)}>
                        {job.is_active ? 'Close' : 'Reopen'}
                      </button>{' '}
                      <button className="danger small" onClick={() => remove(job)}>
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </>
  )
}
