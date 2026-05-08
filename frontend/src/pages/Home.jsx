import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Avatar, RoleBadge, formatVoice, formatDate, activityLevel, StatCard } from '../components/Common'

const API_URL = import.meta.env.VITE_API_URL || ''

// ── Activity Row Component ───────────────────────────────────────────────────

function ActivityRow({ user, rank, onClick }) {
  const level = activityLevel(user.voice_seconds)
  return (
    <tr
      className={`activity-row activity-${level} cursor-pointer transition-all hover:brightness-110`}
      onClick={() => onClick(user.user_id)}
    >
      <td className="px-4 py-3 text-sm opacity-60 w-12">{rank}</td>

      {/* Игрок */}
      <td className="px-4 py-3 min-w-[200px]">
        <div className="flex items-center gap-3">
          <Avatar url={user.avatar_url} name={user.username} />
          <span className="font-medium truncate">{user.username}</span>
        </div>
      </td>

      {/* Роль */}
      <td className="px-4 py-3">
        <RoleBadge name={user.top_role_name} color={user.top_role_color} />
      </td>

      {/* Сообщения */}
      <td className="px-4 py-3 text-right tabular-nums">
        {(user.message_count || 0).toLocaleString('ru-RU')}
      </td>

      {/* Войс */}
      <td className="px-4 py-3 text-right tabular-nums">
        <span className={`activity-time-${level}`}>
          {formatVoice(user.voice_seconds)}
        </span>
      </td>

      {/* Вступил */}
      <td className="px-4 py-3 text-sm opacity-60 whitespace-nowrap">
        {formatDate(user.server_joined_at)}
      </td>
    </tr>
  )
}

// ── Home Page ───────────────────────────────────────────────────────────────

export default function Home() {
  const navigate = useNavigate()
  const [members, setMembers] = useState([])
  const [roles, setRoles] = useState([])
  const [period, setPeriod] = useState('week')
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedRole, setSelectedRole] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [lastUpdate, setLastUpdate] = useState(null)
  const [countdown, setCountdown] = useState(30)

  const fetchData = useCallback(async () => {
    try {
      setError(null)
      const [membersRes, rolesRes] = await Promise.all([
        fetch(`${API_URL}/top?period=${period}&limit=100`),
        fetch(`${API_URL}/roles`),
      ])

      if (!membersRes.ok) throw new Error(`Ошибка сервера: ${membersRes.status}`)
      if (!rolesRes.ok) throw new Error(`Ошибка сервера: ${rolesRes.status}`)

      const membersJson = await membersRes.json()
      const rolesJson = await rolesRes.json()

      setMembers(membersJson.members || [])
      setRoles(rolesJson.roles || [])
      setLastUpdate(new Date())
      setCountdown(30)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [period])

  useEffect(() => { fetchData() }, [fetchData])

  useEffect(() => {
    const interval = setInterval(fetchData, 30000)
    return () => clearInterval(interval)
  }, [fetchData])

  useEffect(() => {
    const tick = setInterval(() => setCountdown(c => Math.max(0, c - 1)), 1000)
    return () => clearInterval(tick)
  }, [lastUpdate])

  // Фильтрация
  const filteredMembers = members.filter(m => {
    const matchesSearch = !searchQuery || m.username.toLowerCase().includes(searchQuery.toLowerCase())
    const matchesRole = !selectedRole || m.top_role_name === selectedRole
    return matchesSearch && matchesRole
  })

  const stats = {
    high: filteredMembers.filter(m => activityLevel(m.voice_seconds) === 'high').length,
    mid:  filteredMembers.filter(m => activityLevel(m.voice_seconds) === 'mid').length,
    low:  filteredMembers.filter(m => activityLevel(m.voice_seconds) === 'low').length,
  }

  const periodLabels = { week: 'неделя', month: 'месяц', all: 'всё время' }

  return (
    <div className="min-h-screen px-4 py-6" style={{ background: '#05050f' }}>
      {/* ── ШАПКА ── */}
      <header className="max-w-screen-xl mx-auto text-center mb-8">
        <h1 className="text-3xl font-bold tracking-widest flicker neon-cyan" style={{ color: '#00e5ff' }}>
          ◈ ТРЕКЕР АКТИВНОСТИ ◈
        </h1>
        <p className="mt-1 text-xs opacity-40 tracking-widest uppercase">
          Discord Activity Dashboard
        </p>

        <div className="mt-4 flex items-center justify-center gap-4 text-xs opacity-60 flex-wrap">
          {loading ? (
            <span className="neon-purple" style={{ color: '#b400ff' }}>Загрузка...</span>
          ) : error ? (
            <span style={{ color: '#ff1744' }}>⚠ {error}</span>
          ) : (
            <>
              <span>Обновлено: <span style={{ color: '#00e5ff' }}>
                {lastUpdate?.toLocaleTimeString('ru-RU')}
              </span></span>
              <span>•</span>
              <span>Следующее через <span style={{ color: '#b400ff' }}>{countdown}с</span></span>
              <button
                onClick={fetchData}
                className="px-3 py-1 rounded text-xs transition-all hover:brightness-150"
                style={{ border: '1px solid #00e5ff44', color: '#00e5ff', background: '#00e5ff0d' }}
              >
                ↻ Обновить
              </button>
            </>
          )}
        </div>
      </header>

      {/* ── УПРАВЛЕНИЕ ── */}
      <div className="max-w-screen-xl mx-auto mb-6">
        <div className="flex flex-wrap items-center gap-3 mb-4">
          {/* Переключатель периода */}
          <div className="flex items-center gap-2">
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

          {/* Поиск */}
          <input
            type="text"
            placeholder="Поиск по имени..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="px-3 py-1 rounded text-xs w-48"
            style={{
              background: '#0d0d1f',
              border: '1px solid #1a1a3a',
              color: '#fff',
            }}
          />

          {/* Фильтр по роли */}
          <select
            value={selectedRole}
            onChange={(e) => setSelectedRole(e.target.value)}
            className="px-3 py-1 rounded text-xs"
            style={{
              background: '#0d0d1f',
              border: '1px solid #1a1a3a',
              color: '#fff',
            }}
          >
            <option value="">Все роли</option>
            {roles.map(r => (
              <option key={r.name} value={r.name}>{r.name} ({r.count})</option>
            ))}
          </select>
        </div>

        {/* ── СВОДКА ── */}
        <div className="grid grid-cols-3 gap-3">
          <StatCard color="#00ff7f" label="Высокая активность"  value={stats.high} hint="более 10 ч" />
          <StatCard color="#ffd600" label="Средняя активность"  value={stats.mid}  hint="3 – 10 ч" />
          <StatCard color="#ff1744" label="Низкая активность"   value={stats.low}  hint="менее 3 ч" />
        </div>
      </div>

      {/* ── ТАБЛИЦА ── */}
      <div
        className="max-w-screen-xl mx-auto rounded-lg overflow-hidden overflow-x-auto"
        style={{ border: '1px solid #1a1a3a', background: '#0d0d1f' }}
      >
        <table className="w-full">
          <thead>
            <tr className="text-left text-xs opacity-50 uppercase tracking-widest">
              <th className="px-4 py-3 font-normal w-12">#</th>
              <th className="px-4 py-3 font-normal">Игрок</th>
              <th className="px-4 py-3 font-normal">Роль</th>
              <th className="px-4 py-3 font-normal text-right">Сообщения</th>
              <th className="px-4 py-3 font-normal text-right">Войс</th>
              <th className="px-4 py-3 font-normal">Вступил</th>
            </tr>
          </thead>
          <tbody>
            {filteredMembers.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-12 text-center opacity-30">
                  {loading ? 'Загрузка...' : 'Нет данных — бот собирает статистику'}
                </td>
              </tr>
            ) : (
              filteredMembers.map((m, idx) => (
                <ActivityRow
                  key={m.user_id}
                  user={m}
                  rank={idx + 1}
                  onClick={(userId) => navigate(`/profile/${userId}`)}
                />
              ))
            )}
          </tbody>
        </table>
      </div>

      <footer className="max-w-screen-xl mx-auto text-center mt-8 text-xs opacity-20 tracking-widest">
        NEVERLOVE ACTIVITY TRACKER © {new Date().getFullYear()}
      </footer>
    </div>
  )
}