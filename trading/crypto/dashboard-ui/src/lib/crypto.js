// Crypto symbol + price helpers

// BTCUSDT -> BTC
export function symLabel(s) {
  if (typeof s !== 'string') return s
  return s.replace(/USDT$/i, '').replace(/USD$/i, '')
}

// Dynamic decimals: big coins 2dp, small coins up to 5dp
export function priceDecimals(v) {
  const a = Math.abs(v)
  if (a >= 1000) return 2
  if (a >= 1) return 2
  if (a >= 0.1) return 4
  return 5
}

export function fmtPrice(v) {
  if (typeof v !== 'number' || !isFinite(v)) return '—'
  const d = priceDecimals(v)
  return v.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d })
}

// USDT P&L (always 2dp)
export function fmtUsdt(v) {
  if (typeof v !== 'number' || !isFinite(v)) return '—'
  return v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
