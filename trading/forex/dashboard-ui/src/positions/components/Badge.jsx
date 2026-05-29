export default function Badge({ side }) {
  const isLong = side === 'LONG'
  const isShort = side === 'SHORT'
  if (isLong) return (
    <span className="text-[11px] font-bold px-1.5 py-0.5 rounded text-[#0ECB81] bg-[rgba(14,203,129,0.12)] border border-[rgba(14,203,129,0.2)]">
      LONG
    </span>
  )
  if (isShort) return (
    <span className="text-[11px] font-bold px-1.5 py-0.5 rounded text-[#F6465D] bg-[rgba(246,70,93,0.12)] border border-[rgba(246,70,93,0.2)]">
      SHORT
    </span>
  )
  return (
    <span className="text-[11px] font-bold px-1.5 py-0.5 rounded text-[#848E9C] bg-[rgba(132,142,156,0.12)] border border-[rgba(132,142,156,0.15)]">
      HOLD
    </span>
  )
}
