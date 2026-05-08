import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js'
import { Line } from 'react-chartjs-2'
import { Avatar, RoleBadge, formatVoice, formatDate, intToHex } from '../components/Common'

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
)

const API_URL = import.meta.env.VITE_API_URL || ''

const DAYS_OF_WEEK = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

// ── Heatmap Component ────────────────────────────────────────────────────────

function Heatmap({ matrix, maxSeconds }) {
  if (!matrix || matrix.length === 0) return null

  const getColor = (seconds) => {
    if (seconds === 0) return '#1a1a3a'
    const ratio = seconds / (maxSeconds || 1)
    if (ratio < 0.25) return '#0066ff44'
    if (ratio < 0.5) return '#00ff7f66'
    if (ratio < 0.75) return '#ffd60088'
    return '#ff1744aa'
  }

  return (
    <div className="mt-6">
      <h3 className="text-sm font-medium mb-3 opacity-70">📅 Тепловая карта активности (день недели × час)</h3>
      <div className="rounded-lg p-3" style={{ background: '#0d0d1f', border: '1px solid #1a1a3a' }}>
        <div className="flex">
          <div className="flex flex-col gap-1 mr-2 text-xs opacity-50 justify-around">
            {DAYS_OF_WEEK.map(day => <span key={day}>{day}</span>)}
          </div>
          <div className="grid grid-cols-24 gap-0.5">
            {matrix.map((row, dayIdx) =>
              row.map((seconds, hourIdx) => (
                <div
                  key={`${dayIdx}-${hourIdx}`}
                  className="w-3 h-3 rounded-sm"
                  style={{ background: getColor(seconds) }}
                  title={`${DAYS_OF_WEEK[dayIdx]} ${hourIdx}:00-${hourIdx + 1}:00: ${formatVoice(seconds)}`}
                />
              ))
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 mt-3 text-xs opacity-50">
          <span>Меньше</span>
          <div className="flex gap-0.5">
            {['#1a1a3a', '#0066ff44', '#00ff7f66', '#ffd60088', '#ff1744aa'].map((c, i) => (
              <div key={i} className="w-4 h-3 rounded-sm" style={{ background: c }} />
            ))}
          </div>
          <span>Больше</span>
        </div>
      </div>
    </div>
  )
}

// ── Active Hours Component ───────────────────────────────────────────────────

function ActiveHours({ hours, maxSeconds }) {
  if (!hours || hours.length === 0) return null

  const max = maxSeconds || Math.max(...hours, 1)

  return (
    <div className="mt-6">
      <h3 className="text-sm font-medium mb-3 opacity-70">⏰ Активность по часам суток</h3>
      <div className="rounded-lg p-4" style={{ background: '#0d0d1f', border: '1px solid #1a1a3a' }}>
        <div className="flex items-end gap-1 h-32">
          {hours.map((seconds, hour) => {
            const height = (seconds / max) * 100
            return (
              <div
                key={hour}
                className="flex-1 rounded-t transition-all hover:brightness-125"
                style={{
                  height: `${Math.max(height, 2)}%`,
                  background: seconds > 0 ? '#00e5ff' : '#1a1a3a',
                  opacity: seconds > 0 ? 0.6 + (seconds / max) * 0.4 : 0.3,
                }}
                title={`${hour}:00 - ${formatVoice(seconds)}`}
              />
            )
          })}
        </div>
        <div className="flex justify-between text-xs opacity-40 mt-2">
          <span>0:00</span>
          <span>6:00</span>
          <span>12:00</span>
          <span>18:00</span>
          <span>23:00</span>
        </div>
      </div>
    </div>
  )
}

// ── Streaks Component ───────────────────────────────────────────────────────

function Streaks({ streaks }) {
  if (!streaks) return null

  return (
    <div className="grid grid-cols-3 gap-3">
      <div className="rounded-lg px-4 py-3 text-center" style={{ background: '#00e5ff0d', border: '1px solid #00e5ff33' }}>
        <div className="text-xs opacity-60 mb-1">Текущий стрик</div>
        <div className="text-2xl font-bold" style={{ color: '#00e5ff' }}>{streaks.current}</div>
        <div className="text-[10px] opacity-40">дней подряд</div>
      </div>
      <div className="rounded-lg px-4 py-3 text-center" style={{ background: '#ffd6000d', border: '1px solid #ffd60033' }}>
        <div className="text-xs opacity-60 mb-1">Рекорд</div>
        <div className="text-2xl font-bold" style={{ color: '#ffd600' }}>{streaks.longest}</div>
        <div className="text-[10px] opacity-40">дней подряд</div>
      </div>
      <div className="rounded-lg px-4 py-3 text-center" style={{ background: '#b400ff0d', border: '1px solid #b400ff33' }}>
        <div className="text-xs opacity-60 mb-1">Всего дней</div>
        <div className="text-2xl font-bold" style={{ color: '#b400ff' }}>{streaks.active_days_total}</div>
        <div className="text-[10px] opacity-40">с активностью</div>
      </div>
    </div>
  )
}

// ── Activity Chart Component ─────────────────────────────────────────────────

function ActivityChart({ timeline }) {
  if (!timeline || timeline.length === 0) return null

  const labels = timeline.map(t => {
    const date = new Date(t.bucket)
    return date.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })
  })

  const voiceData = timeline.map(t => (t.voice_seconds / 3600).toFixed(1))
  const messageData = timeline.map(t => t.message_count)

  const chartData = {
    labels,
    datasets: [
      {
        label: 'Войс (часы)',
        data: voiceData,
        borderColor: '#00e5ff',
        backgroundColor: 'rgba(0, 229, 255, 0.1)',
        fill: true,
        tension: 0.3,
        yAxisID: 'y',
      },
      {
        label: 'Сообщения',
        data: messageData,
        borderColor: '#b400ff',
        backgroundColor: 'rgba(180, 0, 255, 0.1)',
        fill: true,
        tension: 0.3,
        yAxisID: 'y1',
      },
    ],
  }

  const options = {
    responsive: true,
    interaction: {
      mode: 'index',
      intersect: false,
    },
    plugins: {
      legend: {
        labels: { color: '#888' },
      },
    },
    scales: {
      x: {
        ticks: { color: '#666' },
        grid: { color: '#1a1a3a' },
      },
      y: {
        type: 'linear',
        display: true,
        position: 'left',
        ticks: { color: '#00e5ff' },
        grid: { color: '#1a1a3a' },
        title: { display: true, text: 'Часы', color: '#00e5ff' },
      },
      y1: {
        type: 'linear',
        display: true,
        position: 'right',
        ticks: { color: '#b400ff' },
        grid: { drawOnChartArea: false },
        title: { display: true, text: 'Сообщения', color: '#b400ff' },
      },
    },
  }

  return (
    <div className="mt-6">
      <h3 className="text-sm font-medium mb-3 opacity-70">📈 График активности</h3>
      <div className="rounded-lg p-4" style={{ background: '#0d0d1f', border: '1px solid #1a1a3a' }}>
        <Line data={chartData} options={options} />
      </div>
    </div>
  )
}

// ── Profile Page ─────────────────────────────────────────────────────────────

export default function Profile() {
  const { userId } = useParams()
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [period, setPeriod] = useState('month')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetchProfile()
  }, [userId, period])

  const fetchProfile = async () => {
    try {
      setLoading(true)
      setError(null)
      const res = await fetch(`${API_URL}/profile/${userId}?period=${period}`)
      if (!res.ok) throw new Error('Участник не найден')
      const json = await res.json()
      setData(json)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen px-4 py-6 flex items-center justify-center" style={{ background: '#05050f' }}>
        <div className="text-center">
          <div className="neon-purple" style={{ color: '#b400ff' }}>Загрузка...</div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen px-4 py-6 flex items-center justify-center" style={{ background: '#05050f' }}>
        <div className="text-center">
          <div style={{ color: '#ff1744' }}>⚠ {error}</div>
          <button
            onClick={() => navigate('/')}
            className="mt-4 px-4 py-2 rounded text-sm"
            style={{ border: '1px solid #00e5ff44', color: '#00e5ff', background: '#00e5ff0d' }}
          >
            ← На главную
          </button>
        </div>
      </div>
    )
  }

  const { user, period_stats, prev_period_stats, timeline, heatmap, hours, streaks } = data
  const periodLabels = { week: 'неделю', month: 'месяц', all: 'всё время' }

  const voiceDiff = prev_period_stats
    ? period_stats.voice_seconds - prev_period_stats.voice_seconds
    : null
  const msgDiff = prev_period_stats
    ? period_stats.message_count - prev_period_stats.message_count
    : null

  const maxHeatmapValue = Math.max(...heatmap.flat(), 1)
  const maxHourValue = Math.max(...hours, 1)

  return (
    <div className="min-h-screen px-4 py-6" style={{ background: '#05050f' }}>
      {/* ── ШАПКА ── */}
      <header className="max-w-screen-xl mx-auto mb-6">
        <button
          onClick={() => navigate('/')}
          className="text-sm opacity-60 hover:opacity-100 transition-opacity"
          style={{ color: '#00e5ff' }}
        >
          ← Назад к списку
        </button>

        <div className="mt-4 flex items-center gap-4">
          <Avatar url={user.avatar_url} name={user.username} size="large" />
          <div>
            <h1 className="text-2xl font-bold">{user.username}</h1>
            <RoleBadge name={user.top_role_name} color={user.top_role_color} />
            <div className="text-xs opacity-40 mt-1">
              На сервере с {formatDate(user.server_joined_at)}
            </div>
          </div>
        </div>

        <div className="mt-4 flex items-center gap-2">
          <span className="text-sm opacity-60">Период:</span>
          {['week', 'month', 'all'].map(p => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`px-3 py-1 rounded text-xs transition-all ${
                period === p ? 'brightness-125' : 'opacity-50 hover:opacity-100'
              }`}
              style={{
                border: '1px solid #00e5ff44',
                color: '#00e5ff',
                background: period === p ? '#00e5ff22' : '#00e5ff0d',
              }}
            >
              {periodLabels[p]}
            </button>
          ))}
        </div>
      </header>

      {/* ── СТАТИСТИКА ЗА ПЕРИОД ── */}
      <div className="max-w-screen-xl mx-auto">
        <div className="grid grid-cols-2 gap-3 mb-6">
          <div className="rounded-lg px-5 py-4" style={{ background: '#0d0d1f', border: '1px solid #1a1a3a' }}>
            <div className="text-xs opacity-60 mb-1">Голосовой чат за {periodLabels[period]}</div>
            <div className="text-3xl font-bold" style={{ color: '#00e5ff' }}>
              {formatVoice(period_stats.voice_seconds)}
            </div>
            {voiceDiff !== null && (
              <div className={`text-xs mt-1 ${voiceDiff >= 0 ? 'opacity-60' : 'opacity-40'}`}>
                {voiceDiff >= 0 ? '+' : ''}{formatVoice(voiceDiff)} vs прошлый {periodLabels[period]}
              </div>
            )}
          </div>
          <div className="rounded-lg px-5 py-4" style={{ background: '#0d0d1f', border: '1px solid #1a1a3a' }}>
            <div className="text-xs opacity-60 mb-1">Сообщения за {periodLabels[period]}</div>
            <div className="text-3xl font-bold" style={{ color: '#b400ff' }}>
              {period_stats.message_count.toLocaleString('ru-RU')}
            </div>
            {msgDiff !== null && (
              <div className={`text-xs mt-1 ${msgDiff >= 0 ? 'opacity-60' : 'opacity-40'}`}>
                {msgDiff >= 0 ? '+' : ''}{msgDiff} vs прошлый {periodLabels[period]}
              </div>
            )}
          </div>
        </div>

        {/* ── СТРИКИ ── */}
        <Streaks streaks={streaks} />

        {/* ── ГРАФИК ── */}
        <ActivityChart timeline={timeline} />

        {/* ── HEATMAP ── */}
        <Heatmap matrix={heatmap} maxSeconds={maxHeatmapValue} />

        {/* ── АКТИВНЫЕ ЧАСЫ ── */}
        <ActiveHours hours={hours} maxSeconds={maxHourValue} />
      </div>
    </div>
  )
}