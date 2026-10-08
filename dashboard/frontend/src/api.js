import axios from 'axios'

// All backend calls go through this instance.
// The login token lives in an HttpOnly cookie: the browser sends it automatically,
// and JavaScript can never read it.
const api = axios.create({
  baseURL: '/api',
  timeout: 8000,
})

export const errorMessage = (err) =>
  err?.response?.data?.error || 'Cannot reach the server.'

export default api
