import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { api, rows, getAll } from '../api.js'
import { Banner, Badge } from '../components/Layout.jsx'
import JobForm, { jobToForm } from '../components/JobForm.jsx'

// Recruiter home: create, edit, close/reopen and delete postings.
export default function MyPostings() {
  const [jobs, setJobs] = useState([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [form, setForm] = useState(jobToForm(null))
  const [editingId, setEditingId] = useState(null)

  const load = async () => {
    try {
      setJobs(rows(await getAll('/api/jobs/'))) // recruiter sees own, incl. closed
      setError('')
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const reset = () => {
    setForm(jobToForm(null))
    setEditingId(null)
  }

  const startEdit = (job) => {
    setForm(jobToForm(job))
    setEditingId(job.id)
    setError('')
    setNotice('')
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    setNotice('')
    try {
      if (editingId) {
        await api.patch(`/api/jobs/${editingId}/`, form)
        setNotice('Posting updated.')
      } else {
        const job = await api.post('/api/jobs/', form)
        setNotice(`Posted "${job.title}" (company: ${job.company_name || '—'}).`)
      }
      reset()
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
          <h2>{editingId ? 'Edit posting' : 'Post a new job'}</h2>
          {editingId && (
            <p className="muted">
              Editing posting #{editingId}.{' '}
              <a
                href="#"
                onClick={(e) => {
                  e.preventDefault()
                  reset()
                }}
              >
                Cancel
              </a>
            </p>
          )}
          <JobForm
            form={form}
            onChange={setForm}
            onSubmit={submit}
            busy={busy}
            submitLabel={editingId ? 'Save changes' : 'Publish job'}
          />
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
                      <button
                        className="secondary small"
                        onClick={() => startEdit(job)}
                      >
                        Edit
                      </button>{' '}
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
