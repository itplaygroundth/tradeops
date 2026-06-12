export default function SentimentGauges() {
  return (
    <div className="sentiment-gauges">
      {/* Binance Global */}
      <div className="gauge-card">
        <div className="gauge-label">Binance Global Positions</div>
        <div className="gauge-row">
          <div className="gauge-ring">
            <svg viewBox="0 0 120 120" className="gauge-svg">
              <circle cx="60" cy="60" r="50" fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="8" />
              <circle
                cx="60" cy="60" r="50"
                fill="none" stroke="var(--green)" strokeWidth="8"
                strokeDasharray={`${73 * 3.14} 314`}
                strokeLinecap="round"
                transform="rotate(-90 60 60)"
                opacity="0.9"
              />
              <circle
                cx="60" cy="60" r="50"
                fill="none" stroke="var(--red)" strokeWidth="8"
                strokeDasharray={`${27.3 * 3.14} 314`}
                strokeDashoffset={`${-73 * 3.14}`}
                strokeLinecap="round"
                transform="rotate(-90 60 60)"
                opacity="0.9"
              />
              <text x="60" y="52" textAnchor="middle" fill="var(--text-primary)" fontSize="22" fontWeight="700" fontFamily="JetBrains Mono, monospace">73%</text>
              <text x="60" y="70" textAnchor="middle" fill="var(--text-muted)" fontSize="10">Long</text>
            </svg>
          </div>
          <div className="gauge-side">
            <div className="gauge-side-row">
              <span className="gauge-side-dot" style={{ background: 'var(--green)' }}></span>
              <span>Long</span>
              <strong>73.0%</strong>
            </div>
            <div className="gauge-side-row">
              <span className="gauge-side-dot" style={{ background: 'var(--red)' }}></span>
              <span>Short</span>
              <strong>27.3%</strong>
            </div>
          </div>
        </div>
      </div>

      {/* Top Trader */}
      <div className="gauge-card">
        <div className="gauge-label">Top Trader Positions</div>
        <div className="gauge-row">
          <div className="gauge-ring">
            <svg viewBox="0 0 120 120" className="gauge-svg">
              <circle cx="60" cy="60" r="50" fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="8" />
              <circle
                cx="60" cy="60" r="50"
                fill="none" stroke="var(--green)" strokeWidth="8"
                strokeDasharray={`${57 * 3.14} 314`}
                strokeLinecap="round"
                transform="rotate(-90 60 60)"
                opacity="0.9"
              />
              <circle
                cx="60" cy="60" r="50"
                fill="none" stroke="var(--red)" strokeWidth="8"
                strokeDasharray={`${42.9 * 3.14} 314`}
                strokeDashoffset={`${-57 * 3.14}`}
                strokeLinecap="round"
                transform="rotate(-90 60 60)"
                opacity="0.9"
              />
              <text x="60" y="52" textAnchor="middle" fill="var(--text-primary)" fontSize="22" fontWeight="700" fontFamily="JetBrains Mono, monospace">57%</text>
              <text x="60" y="70" textAnchor="middle" fill="var(--text-muted)" fontSize="10">Long</text>
            </svg>
          </div>
          <div className="gauge-side">
            <div className="gauge-side-row">
              <span className="gauge-side-dot" style={{ background: 'var(--green)' }}></span>
              <span>Long</span>
              <strong>57.0%</strong>
            </div>
            <div className="gauge-side-row">
              <span className="gauge-side-dot" style={{ background: 'var(--red)' }}></span>
              <span>Short</span>
              <strong>42.9%</strong>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
