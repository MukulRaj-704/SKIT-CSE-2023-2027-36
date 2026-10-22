// Shared posting form used by "new job" and "edit job" so both paths send
// exactly the same payload to the API.
const EMPTY = {
  title: '',
  location: '',
  job_type: 'full_time',
  salary_range: '',
  description: '',
  requirements: '',
}

const JOB_TYPES = [
  ['full_time', 'Full time'],
  ['part_time', 'Part time'],
  ['contract', 'Contract'],
  ['internship', 'Internship'],
]

// job -> form state (null/'' becomes the empty default).
export function jobToForm(job) {
  if (!job) return { ...EMPTY }
  return {
    title: job.title || '',
    location: job.location || '',
    job_type: job.job_type || 'full_time',
    salary_range: job.salary_range || '',
    description: job.description || '',
    requirements: job.requirements || '',
  }
}

export default function JobForm({ form, onChange, onSubmit, busy, submitLabel = 'Save' }) {
  const set = (key) => (e) => onChange({ ...form, [key]: e.target.value })

  return (
    <form onSubmit={onSubmit}>
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
            {JOB_TYPES.map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
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
        placeholder="Requirements: Python, Django, PostgreSQL…"
        required
        minLength={30}
      />

      <button disabled={busy}>{busy ? 'Saving…' : submitLabel}</button>
    </form>
  )
}