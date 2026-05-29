export default function WalletCard({ summary, mt5 }) {
  if (!summary) return null

  const acct = mt5?.account || summary.account || {}
  const balance = acct.balance || 0
  const equity = acct.equity || 0
  const margin = acct.margin || 0
  const marginFree = acct.margin_free || 0
  const profit = acct.profit || 0
  const leverage = acct.leverage || 0
  const mode = summary.paper_mode ? 'PAPER' : 'LIVE'
  const mt5Online = mt5?.status === 'online'

  return (
    <div className="gauge-card">
      <div className="wallet-card-header">
        <span className="wallet-label-icon">🏦</span>
        <span className="wallet-label-text">MT5 Account</span>
        <span className={`wallet-badge ${mt5Online ? 'live' : 'off'}`}>
          {mt5Online ? 'ONLINE' : mt5?.status === 'offline' ? 'OFFLINE' : mode}
        </span>
      </div>
      <div className="wallet-value-row">
        <span className={`wallet-value ${equity >= balance ? '' : 'muted'}`}>
          ${equity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </span>
        <span className="wallet-currency-tag">{acct.currency || 'USD'}</span>
      </div>
      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4 }}>
        Balance: ${balance.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </div>
      {mt5Online && (
        <div style={{ display: 'flex', gap: 8, marginTop: 6, fontSize: 9, color: 'var(--text-muted)' }}>
          <span>Margin: ${margin.toFixed(2)}</span>
          <span>Free: ${marginFree.toFixed(2)}</span>
          <span style={{ color: profit >= 0 ? 'var(--green)' : 'var(--red)' }}>
            P&L: {profit >= 0 ? '+' : ''}${profit.toFixed(2)}
          </span>
        </div>
      )}
      {mt5Online && leverage > 0 && (
        <div style={{ fontSize: 9, color: 'var(--text-muted)', marginTop: 2 }}>
          Leverage: 1:{leverage}
        </div>
      )}
      {mt5?.status === 'offline' && mt5?.cachedAt && (
        <div style={{ fontSize: 9, color: 'var(--red)', marginTop: 4 }}>
          ⚠ Offline — last seen {new Date(mt5.cachedAt).toLocaleTimeString()}
        </div>
      )}
    </div>
  )
}
