import { useNavigate } from 'react-router-dom'
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

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend)

// PLACEHOLDER DATA: will be replaced by real values from the Flask API.
const labels = ['-50s', '-40s', '-30s', '-20s', '-10s', 'now']
const chartData = {
  labels,
  datasets: [
    { label: 'Temperature (°C)', data: [24.1, 24.2, 24.2, 24.4, 24.3, 24.5], borderColor: '#4f9cf9', tension: 0.3 },
    { label: 'Gas (raw)', data: [310, 312, 309, 315, 311, 313], borderColor: '#f9a84f', tension: 0.3 },
  ],
}
const chartOptions = {
  responsive: true,
  plugins: { legend: { labels: { color: '#c9d1d9' } } },
  scales: {
    x: { ticks: { color: '#8b949e' }, grid: { color: '#21262d' } },
    y: { ticks: { color: '#8b949e' }, grid: { color: '#21262d' } },
  },
}

const stats = [
  { name: 'Temperature', value: '-- °C' },
  { name: 'Gas level', value: '--' },
  { name: 'Presence', value: '--' },
  { name: 'Node status', value: '--' },
]

export default function Dashboard() {
  const navigate = useNavigate()

  return (
    <div className="dashboard">
      <header className="topbar">
        <h1>Sentinel X</h1>
        <button className="secondary" onClick={() => navigate('/')}>Log out</button>
      </header>

      <section className="stats">
        {stats.map((s) => (
          <div className="card" key={s.name}>
            <p className="muted">{s.name}</p>
            <p className="stat-value">{s.value}</p>
          </div>
        ))}
      </section>

      <section className="card">
        <h2>Sensor data (placeholder)</h2>
        <Line data={chartData} options={chartOptions} />
      </section>

      <section className="card">
        <h2>Alerts</h2>
        <p className="muted">No alerts yet. Real alerts will appear here.</p>
      </section>
    </div>
  )
}
