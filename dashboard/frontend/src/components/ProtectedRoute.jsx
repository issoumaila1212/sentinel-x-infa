import { Navigate } from 'react-router-dom'
import { useAuth } from '../auth.jsx'

// Redirects to the login page if nobody is logged in,
// and to the dashboard if the user's role is too low for this page.
export default function ProtectedRoute({ minRole = 'user', children }) {
  const { user, loading, hasRole } = useAuth()
  if (loading) return <div className="center muted">Loading…</div>
  if (!user) return <Navigate to="/" replace />
  if (!hasRole(minRole)) return <Navigate to="/dashboard" replace />
  return children
}
