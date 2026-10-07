import axios from 'axios'

// All backend calls go through this instance.
// In development, '/api' is proxied to Flask (see vite.config.js).
const api = axios.create({
  baseURL: '/api',
  timeout: 8000,
})

export default api
