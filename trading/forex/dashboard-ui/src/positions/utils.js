export const fmtUSD = (v, d = 2) => {
  if (v === null || v === undefined) return '--'
  const a = Math.abs(v)
  const s = v >= 0 ? '+' : '-'
  if (a >= 1000000) return s + '$' + (a / 1000000).toFixed(2) + 'M'
  if (a >= 1000) return s + '$' + (a / 1000).toFixed(2) + 'k'
  return (v >= 0 ? '+' : '') + '$' + v.toFixed(d)
}

export const fmtPrice = (p) => {
  if (!p && p !== 0) return '--'
  if (p >= 10000) return '$' + Number(p).toLocaleString('en', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  if (p >= 100) return '$' + Number(p).toFixed(2)
  if (p >= 1) return '$' + Number(p).toFixed(4)
  return '$' + Number(p).toFixed(6)
}

export const fmtPct = (v, plus = true) => {
  if (v === null || v === undefined) return '--'
  const s = v >= 0 && plus ? '+' : ''
  return s + v.toFixed(2) + '%'
}

export const clrFor = (v) =>
  v > 0 ? '#0ECB81' : v < 0 ? '#F6465D' : '#848E9C'

export const symIcon = (s) => {
  const icons = { BTC: '₿', ETH: 'Ξ', SOL: '◎', BNB: '⬡', XRP: '✕', DOGE: 'Ð', ADA: '₳', AVAX: '▲', LINK: '⬡' }
  const base = (s || '').replace('USDT', '').replace('BUSD', '')
  return icons[base] || base.charAt(0)
}

export const symBase = (s) =>
  (s || '').replace('USDT', '').replace('BUSD', '')
