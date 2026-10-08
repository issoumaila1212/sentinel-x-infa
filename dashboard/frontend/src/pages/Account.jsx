import { useState } from 'react'
import api, { errorMessage } from '../api'
import { useAuth } from '../auth.jsx'
import Topbar from '../components/Topbar.jsx'

export default function Account() {
  const { user } = useAuth()
  const [form, setForm] = useState({ current: '', next: '', repeat: '' })
  const [message, setMessage] = useState(null)

  const set = (field) => (e) => setForm({ ...form, [field]: e.target.value })

  const submit = async (e) => {
    e.preventDefault()
    if (form.next !== form.repeat) {
      setMessage({ type: 'error', text: 'The two new passwords are different.' })
      return
    }
    try {
      await api.post('/auth/password', { current: form.current, new: form.next })
      setForm({ current: '', next: '', repeat: '' })
      setMessage({ type: 'ok', text: 'Password changed.' })
    } catch (err) {
      setMessage({ type: 'error', text: errorMessage(err) })
    }
  }

  return (
    <div className="dashboard">
      <Topbar />
      <section className="card narrow">
        <h2>My account</h2>
        <p className="muted">Signed in as <strong>{user.username}</strong> ({user.role})</p>

        <form onSubmit={submit}>
          <label htmlFor="current">Current password</label>
          <input id="current" type="password" value={form.current} onChange={set('current')}
                 autoComplete="current-password" required />
          <label htmlFor="next">New password (12 characters minimum)</label>
          <input id="next" type="password" value={form.next} onChange={set('next')}
                 autoComplete="new-password" required />
          <label htmlFor="repeat">Repeat new password</label>
          <input id="repeat" type="password" value={form.repeat} onChange={set('repeat')}
                 autoComplete="new-password" required />
          {message && <p className={message.type === 'ok' ? 'success' : 'error'}>{message.text}</p>}
          <button type="submit">Change password</button>
        </form>
      </section>
    </div>
  )
}
