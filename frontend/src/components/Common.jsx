// ── Утилиты ──────────────────────────────────────────────────────────────────

export function formatVoice(seconds) {
  if (!seconds) return '0 ч'
  const hours = seconds / 3600
  if (hours >= 10) return `${Math.floor(hours)} ч`
  if (hours >= 1)  return `${hours.toFixed(1)} ч`
  const minutes = Math.floor(seconds / 60)
  return `${minutes} мин`
}

export function formatDate(ts) {
  if (!ts) return '—'
  const hasTimezone = /[zZ]|[+-]\d{2}:?\d{2}$/.test(ts)
  const normalized = hasTimezone ? ts : ts.replace(' ', 'T') + 'Z'
  const d = new Date(normalized)
  if (isNaN(d.getTime())) return '—'
  return d.toLocaleDateString('ru-RU', {
    day: '2-digit', month: '2-digit', year: 'numeric',
  })
}

export function activityLevel(voiceSeconds) {
  const hours = (voiceSeconds || 0) / 3600
  if (hours > 10) return 'high'
  if (hours >= 3) return 'mid'
  return 'low'
}

export function intToHex(intColor) {
  if (!intColor) return null
  return '#' + intColor.toString(16).padStart(6, '0')
}

// ── Компоненты ────────────────────────────────────────────────────────────────

export function RoleBadge({ name, color }) {
  if (!name) return <span className="opacity-30 text-xs">—</span>
  const hex = intToHex(color) || '#888'
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium whitespace-nowrap"
      style={{
        background: hex + '22',
        color: hex,
        border: `1px solid ${hex}55`,
      }}
    >
      <span className="w-1.5 h-1.5 rounded-full" style={{ background: hex }} />
      {name}
    </span>
  )
}

export function Avatar({ url, name, size = 'normal' }) {
  const sizeClass = size === 'large' ? 'w-16 h-16 text-2xl' : 'w-9 h-9 text-sm'
  if (url) {
    return (
      <img
        src={url}
        alt={name}
        className={`${sizeClass} rounded-full object-cover`}
        style={{ border: '1px solid #1a1a3a' }}
        loading="lazy"
        onError={(e) => { e.currentTarget.style.display = 'none' }}
      />
    )
  }
  return (
    <div
      className={`${sizeClass} rounded-full flex items-center justify-center font-bold`}
      style={{ background: '#1a1a3a', color: '#888' }}
    >
      {(name || '?').charAt(0).toUpperCase()}
    </div>
  )
}

export function StatCard({ color, label, value, hint }) {
  return (
    <div
      className="rounded-lg px-5 py-3 flex items-center justify-between"
      style={{ background: color + '0d', border: `1px solid ${color}33` }}
    >
      <div>
        <div className="text-xs opacity-60">{label}</div>
        <div className="text-[10px] opacity-40">{hint}</div>
      </div>
      <div className="text-2xl font-bold tabular-nums" style={{ color }}>
        {value}
      </div>
    </div>
  )
}