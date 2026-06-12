import { useState } from 'react'

export default function ReportBtn() {
  const [st, setSt] = useState('idle')

  const send = async () => {
    setSt('sending')
    try {
      const r = await fetch('/api/telegram-report', { method: 'POST' })
      const d = await r.json()
      setSt(d.ok ? 'sent' : 'error')
    } catch {
      setSt('error')
    }
    setTimeout(() => setSt('idle'), 3000)
  }

  const labels = { idle: 'Send Report', sending: 'Sending…', sent: '✓ Sent', error: '✕ Failed' }
  const styles = {
    idle: 'bg-[#2B3139] text-[#EAECEF] border-[rgba(255,255,255,0.07)]',
    sending: 'bg-[#2B3139] text-[#848E9C] border-[rgba(255,255,255,0.07)]',
    sent: 'bg-[rgba(14,203,129,0.15)] text-[#0ECB81] border-[rgba(14,203,129,0.25)]',
    error: 'bg-[rgba(246,70,93,0.15)] text-[#F6465D] border-[rgba(246,70,93,0.25)]',
  }

  return (
    <button
      onClick={send}
      disabled={st === 'sending'}
      className={`border rounded-md px-3 py-1.5 text-xs font-semibold transition-all active:scale-95 active:opacity-70 ${styles[st]}`}
      style={{ fontFamily: 'IBM Plex Sans, sans-serif' }}
    >
      {labels[st]}
    </button>
  )
}
