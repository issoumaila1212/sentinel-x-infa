import { useCallback, useMemo } from 'react'
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

// Seuils identiques a server/mqtt_client.py : ici juste pour colorer les
// cartes instantanement. La table `alerts` reste la seule source de verite.
const STATUS_RULES = {
  temperature: [['>', 38, 'critical'], ['>', 30, 'warning'], ['<', 5, 'warning']],
  humidity: [['>', 85, 'warning'], ['<', 15, 'warning']],
  gas: [['>', 700, 'critical'], ['>', 400, 'warning']],
  distance: [['<', 15, 'warning']],
}

function statusOf(key, value) {
  if (value === null || value === undefined) return 'neutral'
  for (const [op, limit, level] of STATUS_RULES[key] || []) {
    if ((op === '>' && value > limit) || (op === '<' && value < limit)) return level
  }
  return 'ok'
}

function chartData(rows, key, label, color) {
  return {
    labels: rows.map((r) => new Date(r.ts).toLocaleTimeString()),
    datasets: [{
      label,
      data: rows.map((r) => r[key]),
      borderColor: color,
      backgroundColor: color,
      tension: 0.35,
      borderWidth: 2,
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
    x: { ticks: { color: '#8b949e', maxTicksLimit: 8 }, grid: { color: '#1c232e' } },
    y: { ticks: { color: '#8b949e' }, grid: { color: '#1c232e' } },
  },
}

// --- Icones (SVG en ligne, zero dependance) ---------------------------------
const IconThermometer = () => (
  <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 14.5V5a2 2 0 1 0-4 0v9.5a4 4 0 1 0 4 0Z" />
  </svg>
)
const IconDroplet = () => (
  <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 3c3.5 4 6 7.2 6 10.5a6 6 0 1 1-12 0C6 10.2 8.5 7 12 3Z" />
  </svg>
)
const IconFlame = () => (
  <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 3c1 3-3 4-3 7a3 3 0 1 0 6 0c0-1-.5-1.8-1-2.5.8.3 2 1.4 2 3.8a5 5 0 1 1-10 0C6 7.5 9 6 12 3Z" />
  </svg>
)
const IconRadar = () => (
  <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="8.5" />
    <circle cx="12" cy="12" r="4" />
    <path d="M12 12 17.5 6.5" />
  </svg>
)
const IconMotion = () => (
  <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="5" r="1.6" fill="currentColor" stroke="none" />
    <path d="M9 21l1.5-5.5L8 13l1-4.5c.3-1.3 1.3-2 2.6-2h.8c1.3 0 2.3.7 2.6 2l1 4.5-2.5 2.5L15 21" />
  </svg>
)
const IconPulse = () => (
  <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 12h4l2-7 4 14 2-7h6" />
  </svg>
)
const IconShieldCheck = () => (
  <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 3l7 3v6c0 5-3.2 8.2-7 9-3.8-.8-7-4-7-9V6z" />
    <path d="M9 12.5l2 2 4-4.5" />
  </svg>
)
const IconShieldAlert = () => (
  <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 3l7 3v6c0 5-3.2 8.2-7 9-3.8-.8-7-4-7-9V6z" />
    <path d="M12 8v4.5M12 16h.01" />
  </svg>
)

const ALERT_ICON = {
  critical: () => (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2 1 21h22Z" /><path d="M12 9v5M12 17h.01" />
    </svg>
  ),
  warning: () => (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9" /><path d="M12 8v5M12 16h.01" />
    </svg>
  ),
  info: () => (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9" /><path d="M12 11v4M12 8h.01" />
    </svg>
  ),
}

export default function Dashboard() {
  const { hasRole } = useAuth()
  const sensors = usePolling(getSensors, 2000)
  const status = usePolling(getStatus, 2000)
  const alerts = usePolling(getAlerts, 5000)

  const latest = useMemo(() => {
    const list = sensors.data || []
    if (!list.length) return undefined
    // plusieurs devices peuvent apparaître (ex: ancien nom de test) :
    // on garde celui qui a vraiment parlé le plus récemment.
    return list.reduce((a, b) => (new Date(a.ts) > new Date(b.ts) ? a : b))
  }, [sensors.data])
  const device = latest?.device
  const getReadings = useCallback(
    () => api.get('/readings', { params: { device, limit: 60 } }).then((r) => r.data),
    [device],
  )
  const readings = usePolling(getReadings, 2000, Boolean(device))
  const rows = readings.data || []
  const hasTemperature = rows.some((r) => r.temperature !== null)
  const hasHumidity = rows.some((r) => r.humidity !== null)
  const hasDistance = rows.some((r) => r.distance !== null)
  const hasGas = rows.some((r) => r.gas !== null)

  const online = status.data?.online
  const apiDown = sensors.error || status.error

  const acknowledge = async (id) => {
    await api.post('/alert/ack', { id })
    alerts.refresh()
  }

  const unacked = useMemo(() => (alerts.data || []).filter((a) => !a.acknowledged), [alerts.data])
  const worstLevel = unacked.some((a) => a.level === 'critical')
    ? 'critical'
    : unacked.some((a) => a.level === 'warning')
      ? 'warning'
      : 'ok'

  const bannerText = {
    ok: ['Système sécurisé', 'Aucune anomalie active sur le site.'],
    warning: [`${unacked.length} alerte(s) en attente`, 'Vérifie les alertes ci-dessous.'],
    critical: [`${unacked.length} alerte(s) critique(s)`, 'Intervention requise immédiatement.'],
  }[worstLevel]

  const cards = [
    { key: 'temperature', name: 'Température', value: fmt(latest?.temperature, ' °C'), icon: IconThermometer, status: statusOf('temperature', latest?.temperature) },
    { key: 'humidity', name: 'Humidité', value: fmt(latest?.humidity, ' %'), icon: IconDroplet, status: statusOf('humidity', latest?.humidity) },
    { key: 'gas', name: 'Gaz', value: fmt(latest?.gas), icon: IconFlame, status: statusOf('gas', latest?.gas) },
    { key: 'distance', name: 'Distance', value: fmt(latest?.distance, ' cm'), icon: IconRadar, status: statusOf('distance', latest?.distance) },
    {
      key: 'presence',
      name: 'Mouvement',
      icon: IconMotion,
      value: latest?.presence == null ? '—' : latest.presence ? 'Détecté' : 'Aucun',
      status: latest?.presence ? 'warning' : 'ok',
    },
    {
      key: 'node',
      name: 'État du nœud',
      icon: IconPulse,
      value: status.data ? (online ? 'En ligne' : 'Hors ligne') : '—',
      sub: status.data?.age_seconds != null ? `dernière donnée il y a ${status.data.age_seconds}s` : 'pas encore de donnée',
      status: status.data ? (online ? 'ok' : 'critical') : 'neutral',
    },
  ]

  return (
    <div className="dashboard">
      <Topbar />
      {apiDown && <div className="banner">Impossible de joindre l'API. Nouvelle tentative…</div>}

      <div className={`status-banner banner-${worstLevel}`}>
        {worstLevel === 'ok' ? <IconShieldCheck /> : <IconShieldAlert />}
        <div className="status-banner-text">
          <span>{bannerText[0]}</span>
          <span className="muted small">{bannerText[1]}</span>
        </div>
      </div>

      <section className="stats">
        {cards.map((c) => {
          const Icon = c.icon
          return (
            <div className={`card stat-card ${c.status}`} key={c.key}>
              <div className="stat-icon"><Icon /></div>
              <div>
                <p className="muted small">{c.name}</p>
                <p className={`stat-value ${c.status}`}>{c.value}</p>
                {c.sub && <p className="muted small">{c.sub}</p>}
              </div>
            </div>
          )
        })}
      </section>

      <section className="charts-grid">
        {hasTemperature && (
          <div className="card">
            <h2>Température {device && <span className="muted small">({device})</span>}</h2>
            <Line data={chartData(rows, 'temperature', 'Température (°C)', '#4f9cf9')} options={chartOptions} />
          </div>
        )}

        {hasHumidity && (
          <div className="card">
            <h2>Humidité</h2>
            <Line data={chartData(rows, 'humidity', 'Humidité (%)', '#58d0c9')} options={chartOptions} />
          </div>
        )}

        {hasDistance && (
          <div className="card">
            <h2>Distance</h2>
            <Line data={chartData(rows, 'distance', 'Distance (cm)', '#c38bf9')} options={chartOptions} />
          </div>
        )}

        {hasGas && (
          <div className="card">
            <h2>Gaz</h2>
            <Line data={chartData(rows, 'gas', 'Gaz (brut, 0–1023)', '#f9a84f')} options={chartOptions} />
          </div>
        )}

        {!hasTemperature && !hasHumidity && !hasDistance && !hasGas && (
          <div className="card">
            <p className="muted">En attente de données…</p>
          </div>
        )}
      </section>

      <section className="card">
        <h2>Alertes</h2>
        {alerts.data?.length ? (
          <ul className="alerts">
            {alerts.data.map((a) => {
              const AlertIcon = ALERT_ICON[a.level] || ALERT_ICON.info
              return (
                <li key={a.id} className={`alert-item level-${a.level} ${a.acknowledged ? 'done' : ''}`}>
                  <span className="alert-icon"><AlertIcon /></span>
                  <span className="grow">
                    {a.message}
                    <span className="muted small"> · {a.source} · {a.device} · {new Date(a.ts).toLocaleString()}</span>
                  </span>
                  {a.acknowledged ? (
                    <span className="muted small">traité</span>
                  ) : (
                    hasRole('admin') && (
                      <button className="secondary" onClick={() => acknowledge(a.id)}>Traiter</button>
                    )
                  )}
                </li>
              )
            })}
          </ul>
        ) : (
          <p className="muted">Aucune alerte.</p>
        )}
      </section>
    </div>
  )
}
