import { useCallback } from 'react'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
} from 'chart.js'
import { Line } from 'react-chartjs-2'
import api from '../api'
import { useAuth } from '../auth.jsx'
import usePolling from '../usePolling.js'
import Topbar from '../components/Topbar.jsx'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend)

const getSensors = () => api.get('/sensors').then((r) => r.data)
const getStatus = () => api.get('/status').then((r) => r.data)
const getAlerts = () => api.get('/alerts').then((r) => r.data)

const fmt = (value, unit = '') => (value === null || value === undefined ? '—' : `${value}${unit}`)

function chartData(rows, key, label, color) {
  return {
    labels: rows.map((r) => new Date(r.ts).toLocaleTimeString()),
    datasets: [{
      label,
      data: rows.map((r) => r[key]),
      borderColor: color,
      tension: 0.3,
      pointRadius: 0,
      spanGaps: true,
    }],
  }
}

const chartOptions = {
  animation: false,
  responsive: true,
  plugins: { legend: { labels: { color: '#c9d1d9' } } },
  scales: {
    x: { ticks: { color: '#8b949e', maxTicksLimit: 8 }, grid: { color: '#21262d' } },
    y: { ticks: { color: '#8b949e' }, grid: { color: '#21262d' } },
  },
}

export default function Dashboard() {
  const { hasRole } = useAuth()
  const sensors = usePolling(getSensors, 2000)
  const status = usePolling(getStatus, 2000)
  const alerts = usePolling(getAlerts, 5000)

  const latest = sensors.data?.[0]
  const device = latest?.device
  const getReadings = useCallback(
    () => api.get('/readings', { params: { device, limit: 60 } }).then((r) => r.data),
    [device],
  )
  const readings = usePolling(getReadings, 2000, Boolean(device))
  const rows = readings.data || []
  const hasTemperature = rows.some((r) => r.temperature !== null)

  const online = status.data?.online
  const apiDown = sensors.error || status.error

  const acknowledge = async (id) => {
    await api.post('/alert/ack', { id })
    alerts.refresh()
  }

  const cards = [
    { name: 'Gas level', value: fmt(latest?.gas) },
    { name: 'Temperature', value: fmt(latest?.temperature, ' °C') },
    { name: 'Presence', value: latest?.presence == null ? '—' : latest.presence ? 'Detected' : 'None' },
    {
      name: 'Node status',
      value: status.data ? (online ? 'Online' : 'Offline') : '—',
      sub: status.data?.age_seconds != null ? `last data ${status.data.age_seconds}s ago` : 'no data yet',
      tone: status.data ? (online ? 'ok' : 'bad') : '',
    },
  ]

  return (
    <div className="dashboard">
      <Topbar />
      {apiDown && <div className="banner">Cannot reach the API. Retrying…</div>}

      <section className="stats">
        {cards.map((c) => (
          <div className="card" key={c.name}>
            <p className="muted">{c.name}</p>
            <p className={`stat-value ${c.tone || ''}`}>{c.value}</p>
            {c.sub && <p className="muted small">{c.sub}</p>}
          </div>
        ))}
      </section>

      <section className="card">
        <h2>Gas level {device && <span className="muted small">({device})</span>}</h2>
        {rows.length ? (
          <Line data={chartData(rows, 'gas', 'Gas (raw, 0–1023)', '#f9a84f')} options={chartOptions} />
        ) : (
          <p className="muted">Waiting for sensor data…</p>
        )}
      </section>

      {hasTemperature && (
        <section className="card">
          <h2>Temperature</h2>
          <Line data={chartData(rows, 'temperature', 'Temperature (°C)', '#4f9cf9')} options={chartOptions} />
        </section>
      )}

      <section className="card">
        <h2>Alerts</h2>
        {alerts.data?.length ? (
          <ul className="alerts">
            {alerts.data.map((a) => (
              <li key={a.id} className={a.acknowledged ? 'done' : ''}>
                <span className={`badge level-${a.level}`}>{a.level || 'info'}</span>
                <span className="grow">
                  {a.message}
                  <span className="muted small"> · {a.source} · {new Date(a.ts).toLocaleString()}</span>
                </span>
                {a.acknowledged ? (
                  <span className="muted small">acknowledged</span>
                ) : (
                  hasRole('admin') && (
                    <button className="secondary" onClick={() => acknowledge(a.id)}>Acknowledge</button>
                  )
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">No alerts.</p>
        )}
      </section>
    </div>
  )
}
