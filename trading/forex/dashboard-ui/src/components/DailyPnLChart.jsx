// Simple SVG Bar Chart — Daily PnL
// No external dependencies, pure SVG

const WIDTH = 280
const HEIGHT = 65
const PAD = { top: 4, right: 4, bottom: 16, left: 4 }

export default function DailyPnLChart({ dailyPnl = {} }) {
  const entries = Object.entries(dailyPnl || {})
  if (!entries.length) {
    return (
      <div className="chart-empty">
        <span className="chart-empty-text">No daily data yet</span>
      </div>
    )
  }

  // Show last 7 days
  const days = entries.slice(-7)
  const vals = days.map(([, v]) => v)
  const maxVal = Math.max(...vals.map(Math.abs), 1)
  const chartW = WIDTH - PAD.left - PAD.right
  const chartH = HEIGHT - PAD.top - PAD.bottom
  const barW = Math.max(4, (chartW / days.length) - 4)

  return (
    <div className="chart-card">
      <div className="chart-header">
        <span className="chart-title">📊 Daily PnL</span>
        <span className="chart-subtitle">Last {days.length}d</span>
      </div>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="chart-svg">
        {/* Zero line */}
        <line x1={PAD.left} y1={PAD.top + chartH / 2}
              x2={WIDTH - PAD.right} y2={PAD.top + chartH / 2}
              stroke="rgba(255,255,255,0.08)" strokeWidth="0.5" />

        {days.map(([date, value], i) => {
          const isUp = value >= 0
          const barH = (Math.abs(value) / maxVal) * (chartH / 2 - 2)
          const x = PAD.left + i * (chartW / days.length) + 2
          const y = isUp
            ? PAD.top + chartH / 2 - barH
            : PAD.top + chartH / 2

          // Short date label
          const label = date.slice(5) // "05-16"

          return (
            <g key={date}>
              <rect x={x} y={y} width={barW} height={Math.max(1, barH)}
                    rx="2" ry="2"
                    fill={isUp ? 'var(--green)' : 'var(--red)'}
                    opacity="0.7" />
              <text x={x + barW / 2} y={HEIGHT - 2} textAnchor="middle"
                    fill="var(--text-muted)" fontSize="6" fontFamily="monospace">
                {label}
              </text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}
