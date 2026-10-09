import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth.jsx'

const BrandIcon = () => (
  <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 3l7 3v6c0 5-3.2 8.2-7 9-3.8-.8-7-4-7-9V6z" />
    <path d="M9 12.5l2 2 4-4.5" />
  </svg>
)

export default function Topbar() {
  const { user, logout, hasRole } = useAuth()
  const navigate = useNavigate()

  const onLogout = async () => {
    await logout()
    navigate('/')
  }

  return (
    <header className="topbar">
      <div className="brand"><BrandIcon /> Sentinel X</div>
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
