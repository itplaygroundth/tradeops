// Simple SVG Line Chart — Equity Curve
// No external dependencies, pure SVG

const WIDTH = 280
const HEIGHT = 90
const PAD = { top: 8, right: 8, bottom: 18, left: 38 }

export default function EquityCurveChart({ data = [] }) {
  if (!data || data.length < 2) {
    return (
      <div className="chart-empty">
        <span className="chart-empty-text">Waiting for equity data...</span>
      </div>
    )
  }

  // Limit to last 200 points for performance
  const points = data.slice(-200)
  const vals = points.map(p => p.total_equity || 0)
  const min = Math.min(...vals) * 0.999
  const max = Math.max(...vals) * 1.001
  const range = max - min || 1

  const chartW = WIDTH - PAD.left - PAD.right
  const chartH = HEIGHT - PAD.top - PAD.bottom

  const scaleX = i => PAD.left + (i / (points.length - 1)) * chartW
  const scaleY = v => PAD.top + chartH - ((v - min) / range) * chartH

  const linePath = points.map((p, i) =>
    `${i === 0 ? 'M' : 'L'}${scaleX(i)},${scaleY(p.total_equity || 0)}`
  ).join(' ')

  const lastVal = vals[vals.length - 1]
  const firstVal = vals[0]
  const change = lastVal - firstVal
  const pctChange = firstVal !== 0 ? ((change / firstVal) * 100) : 0
  const isUp = change >= 0

  // Grid lines
  const gridLines = 4
  const gridYs = Array.from({ length: gridLines + 1 }, (_, i) =>
    min + (range * i / gridLines)
  )

  // Area fill
  const areaPath = `${linePath} L${scaleX(points.length - 1)},${HEIGHT - PAD.bottom} L${scaleX(0)},${HEIGHT - PAD.bottom} Z`

  return (
    <div className="chart-card">
      <div className="chart-header">
        <span className="chart-title">📈 Equity Curve</span>
        <span className={`chart-change ${isUp ? 'up' : 'down'}`}>
          {isUp ? '+' : ''}{pctChange.toFixed(2)}%
        </span>
      </div>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="chart-svg">
        {/* Grid */}
        {gridYs.map((v, i) => (
          <g key={i}>
            <line x1={PAD.left} y1={scaleY(v)} x2={WIDTH - PAD.right} y2={scaleY(v)}
                  stroke="rgba(255,255,255,0.04)" strokeWidth="0.5" />
            <text x={PAD.left - 4} y={scaleY(v) + 3} textAnchor="end"
                  fill="var(--text-muted)" fontSize="7" fontFamily="monospace">
              ${v.toFixed(0)}
            </text>
          </g>
        ))}
        {/* Area fill */}
        <path d={areaPath} fill={isUp ? 'rgba(52,199,89,0.06)' : 'rgba(255,69,58,0.06)'} />
        {/* Line */}
        <path d={linePath} fill="none" stroke={isUp ? 'var(--green)' : 'var(--red)'}
              strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        {/* Latest point */}
        <circle cx={scaleX(points.length - 1)} cy={scaleY(lastVal)} r="2.5"
                fill={isUp ? 'var(--green)' : 'var(--red)'} />
      </svg>
    </div>
  )
}
