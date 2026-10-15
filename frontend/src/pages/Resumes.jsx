import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import { api, rows } from '../api.js'
import { Banner, Badge } from '../components/Layout.jsx'

// Seeker home: upload a PDF (parse-once) and manage own resumes.
export default function Resumes() {
  const [list, setList] = useState([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const fileRef = useRef()

  const load = async () => {
    try {
      setList(rows(await api.get('/api/resumes/')))
      setError('')
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const upload = async (e) => {
    e.preventDefault()
    const file = fileRef.current.files[0]
    if (!file) return
    setError('')
    setNotice('')
    setBusy(true)
    try {
      const data = new FormData()
      data.append('file', file)
      await api.upload('/api/resumes/', data)
      fileRef.current.value = ''
      setNotice(
        `Uploaded — the engine parsed it inline (${file.name}). Check the status below.`,
      )
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const remove = async (resume) => {
    if (!window.confirm(`Delete "${resume.title}" and its stored file?`)) return
    try {
      await api.delete(`/api/resumes/${resume.id}/`)
      await load()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <>
      <h1>My resumes</h1>

      <div className="card">
        <h2>Upload a PDF</h2>
        <Banner kind="ok">{notice}</Banner>
        <Banner kind="error">{error}</Banner>
        <form onSubmit={upload}>
          <input type="file" accept="application/pdf,.pdf" ref={fileRef} required />
          <button disabled={busy}>{busy ? 'Uploading & parsing…' : 'Upload'}</button>
        </form>
        <p className="muted">
          Parsed once on upload; every later score reads the stored JSON — the PDF
          is never re-read.
        </p>
      </div>

      <div className="card">
        <h2>{list.length} resume{list.length === 1 ? '' : 's'}</h2>
        {list.length === 0 && <p className="muted">Nothing yet — upload your first resume above.</p>}
        {list.length > 0 && (
          <table className="list">
            <thead>
              <tr>
                <th>Title</th>
                <th>Parse</th>
                <th>Skills</th>
                <th>Default</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {list.map((r) => (
                <tr key={r.id}>
                  <td>
                    <Link to={`/resumes/${r.id}`}>{r.title || r.original_filename}</Link>
                  </td>
                  <td>
                    <Badge status={r.parse_status} />
                    {r.parse_error && (
                      <div className="muted" style={{ fontSize: 12 }}>{r.parse_error}</div>
                    )}
                  </td>
                  <td>
                    {(r.skills || []).slice(0, 5).map((s) => (
                      <span className="chip" key={s}>{s}</span>
                    ))}
                    {r.skills?.length > 5 && (
                      <span className="chip">+{r.skills.length - 5}</span>
                    )}
                  </td>
                  <td>{r.is_default ? '★' : '—'}</td>
                  <td>
                    <button className="secondary small" onClick={() => remove(r)}>
                      Delete
                    </button>
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
