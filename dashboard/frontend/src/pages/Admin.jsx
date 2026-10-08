import { useState } from 'react'
import api, { errorMessage } from '../api'
import { useAuth } from '../auth.jsx'
import usePolling from '../usePolling.js'
import Topbar from '../components/Topbar.jsx'

const getUsers = () => api.get('/users').then((r) => r.data)
const getAudit = () => api.get('/audit', { params: { limit: 100 } }).then((r) => r.data)

const when = (ts) => (ts ? new Date(ts).toLocaleString() : '—')

export default function Admin() {
  const { user, hasRole } = useAuth()
  const isSuper = hasRole('superadmin')
  const users = usePolling(getUsers, 10000)
  const audit = usePolling(getAudit, 10000, isSuper)

  const roleOptions = isSuper ? ['user', 'admin', 'superadmin'] : ['user', 'admin']
  const [form, setForm] = useState({ username: '', password: '', role: 'user' })
  const [message, setMessage] = useState(null)

  const set = (field) => (e) => setForm({ ...form, [field]: e.target.value })

  // The server enforces these rules too; this only hides what the user cannot do.
  const canEdit = (target) => target.id !== user.id && (isSuper || target.role === 'user')

  const update = async (id, changes) => {
    try {
      await api.patch(`/users/${id}`, changes)
      setMessage(null)
      users.refresh()
      if (isSuper) audit.refresh()
    } catch (err) {
      setMessage({ type: 'error', text: errorMessage(err) })
    }
  }

  const createUser = async (e) => {
    e.preventDefault()
    try {
      await api.post('/users', form)
      setForm({ username: '', password: '', role: 'user' })
      setMessage({ type: 'ok', text: 'Account created.' })
      users.refresh()
      if (isSuper) audit.refresh()
    } catch (err) {
      setMessage({ type: 'error', text: errorMessage(err) })
    }
  }

  return (
    <div className="dashboard">
      <Topbar />

      <section className="card">
        <h2>Users</h2>
        {message && <p className={message.type === 'ok' ? 'success' : 'error'}>{message.text}</p>}
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Username</th><th>Role</th><th>Status</th><th>Last login</th><th /></tr>
            </thead>
            <tbody>
              {(users.data || []).map((u) => (
                <tr key={u.id}>
                  <td>{u.username}{u.id === user.id && <span className="muted small"> (you)</span>}</td>
                  <td>
                    {canEdit(u) ? (
                      <select value={u.role} onChange={(e) => update(u.id, { role: e.target.value })}>
                        {roleOptions.map((r) => <option key={r} value={r}>{r}</option>)}
                      </select>
                    ) : (
                      <span className={`badge role-${u.role}`}>{u.role}</span>
                    )}
                  </td>
                  <td>{u.active ? 'active' : <span className="bad">disabled</span>}</td>
                  <td>{when(u.last_login)}</td>
                  <td>
                    {canEdit(u) && (
                      <button className="secondary" onClick={() => update(u.id, { active: !u.active })}>
                        {u.active ? 'Disable' : 'Enable'}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        <h2>Create an account</h2>
        <form onSubmit={createUser} className="row-form">
          <div>
            <label htmlFor="new-username">Username</label>
            <input id="new-username" value={form.username} onChange={set('username')}
                   autoComplete="off" required />
          </div>
          <div>
            <label htmlFor="new-password">Password (12+ characters)</label>
            <input id="new-password" type="password" value={form.password} onChange={set('password')}
                   autoComplete="new-password" required />
          </div>
          <div>
            <label htmlFor="new-role">Role</label>
            <select id="new-role" value={form.role} onChange={set('role')}>
              {roleOptions.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
          <button type="submit">Create</button>
        </form>
      </section>

      {isSuper && (
        <section className="card">
          <h2>Security log</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Time</th><th>User</th><th>IP</th><th>Event</th><th>Result</th><th>Detail</th></tr>
              </thead>
              <tbody>
                {(audit.data || []).map((a) => (
                  <tr key={a.id}>
                    <td>{when(a.ts)}</td>
                    <td>{a.username || '—'}</td>
                    <td>{a.ip || '—'}</td>
                    <td>{a.action}</td>
                    <td>{a.success ? <span className="ok">ok</span> : <span className="bad">failed</span>}</td>
                    <td className="muted">{a.detail || ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  )
}
