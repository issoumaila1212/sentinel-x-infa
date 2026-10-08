import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth.jsx'

export default function Topbar() {
  const { user, logout, hasRole } = useAuth()
  const navigate = useNavigate()

  const onLogout = async () => {
    await logout()
    navigate('/')
  }

  return (
    <header className="topbar">
      <div className="brand">Sentinel X</div>
      <nav>
        <NavLink to="/dashboard">Dashboard</NavLink>
        {hasRole('admin') && <NavLink to="/admin">Administration</NavLink>}
        <NavLink to="/account">Account</NavLink>
      </nav>
      <div className="who">
        <span className={`badge role-${user.role}`}>{user.role}</span>
        <span>{user.username}</span>
        <button className="secondary" onClick={onLogout}>Log out</button>
      </div>
    </header>
  )
}
