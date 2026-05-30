import { useEffect, useRef, useState } from 'react'
import { createChart, CandlestickSeries, HistogramSeries } from 'lightweight-charts'

const THEME = {
  layout: {
    background: { color: '#0a0a0f' },
    textColor: '#5a5a72',
    fontFamily: "'JetBrains Mono', 'SF Mono', monospace",
    fontSize: 10,
  },
  grid: {
    vertLines: { color: 'rgba(255,255,255,0.04)' },
    horzLines: { color: 'rgba(255,255,255,0.04)' },
  },
  crosshair: { mode: 0 },
  rightPriceScale: { borderColor: 'rgba(255,255,255,0.08)' },
  timeScale: {
    borderColor: 'rgba(255,255,255,0.08)',
    timeVisible: true,
    secondsVisible: false,
  },
}

function parseOhlcv(raw) {
  if (!raw || raw.mt5_status === 'offline') return []
  const arr = Array.isArray(raw)
    ? raw
    : Object.entries(raw)
        .filter(([k]) => !isNaN(Number(k)))
        .sort(([a], [b]) => Number(a) - Number(b))
        .map(([, v]) => v)
  return arr.filter(c => c && typeof c.time === 'number' && c.open != null)
}

export default function TvChart({ symbol, timeframe = 'M15', height, showVolume = true, showCrosshair = true }) {
  // height undefined => fill parent container (responsive)
  const fillParent = height == null
  const containerRef = useRef(null)
  const chartRef = useRef(null)
  const candleRef = useRef(null)
  const volumeRef = useRef(null)
  const [tooltip, setTooltip] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Create chart on mount
  useEffect(() => {
    if (!containerRef.current) return
    const chart = createChart(containerRef.current, {
      ...THEME,
      width: containerRef.current.clientWidth,
      height: containerRef.current.clientHeight || height || 300,
      handleScroll: true,
      handleScale: true,
    })
    chartRef.current = chart

    const candle = chart.addSeries(CandlestickSeries, {
      upColor: '#34c759',
      downColor: '#ff453a',
      borderVisible: false,
      wickUpColor: '#34c759',
      wickDownColor: '#ff453a',
    })
    candleRef.current = candle

    if (showVolume) {
      const vol = chart.addSeries(HistogramSeries, {
        color: 'rgba(0,122,255,0.3)',
        priceFormat: { type: 'volume' },
        priceScaleId: 'volume',
      })
      chart.priceScale('volume').applyOptions({
        scaleMargins: { top: 0.82, bottom: 0 },
      })
      volumeRef.current = vol
    }

    if (showCrosshair) {
      chart.subscribeCrosshairMove(param => {
        if (!param.point || !param.seriesData || !param.seriesData.get(candle)) {
          setTooltip(null)
          return
        }
        const c = param.seriesData.get(candle)
        if (!c) { setTooltip(null); return }
        setTooltip({
          open: c.open?.toFixed(5),
          high: c.high?.toFixed(5),
          low: c.low?.toFixed(5),
          close: c.close?.toFixed(5),
          isUp: c.close >= c.open,
        })
      })
    }

    const ro = new ResizeObserver(entries => {
      const rect = entries[0]?.contentRect
      if (rect?.width) {
        chart.applyOptions(fillParent
          ? { width: rect.width, height: rect.height }
          : { width: rect.width })
      }
    })
    ro.observe(containerRef.current)

    return () => {
      ro.disconnect()
      chart.remove()
      chartRef.current = null
      candleRef.current = null
      volumeRef.current = null
    }
  }, [height, fillParent, showVolume, showCrosshair])

  // Fetch data on symbol/timeframe change
  useEffect(() => {
    if (!candleRef.current) return
    let cancelled = false
    setLoading(true)
    setError(null)

    fetch(`/api/mt5/ohlcv/${symbol}?timeframe=${timeframe}&count=200`)
      .then(r => r.json())
      .then(raw => {
        if (cancelled) return
        const candles = parseOhlcv(raw)
        if (!candles.length) { setError('No data'); setLoading(false); return }
        candleRef.current.setData(candles)
        if (volumeRef.current) {
          volumeRef.current.setData(candles.map(c => ({
            time: c.time,
            value: c.volume ?? 0,
            color: c.close >= c.open ? 'rgba(52,199,89,0.25)' : 'rgba(255,69,58,0.25)',
          })))
        }
        chartRef.current?.timeScale().fitContent()
        setLoading(false)
      })
      .catch(() => {
        if (!cancelled) { setError('Fetch failed'); setLoading(false) }
      })

    return () => { cancelled = true }
  }, [symbol, timeframe])

  return (
    <div style={{ position: 'relative', width: '100%', height: fillParent ? '100%' : height, flex: fillParent ? 1 : undefined }}>
      <div ref={containerRef} style={{ width: '100%', height: '100%' }} />

      {loading && (
        <div style={{
          position: 'absolute', inset: 0, display: 'flex', alignItems: 'center',
          justifyContent: 'center', fontSize: 11, color: 'var(--text-muted)',
          background: '#0a0a0f', fontFamily: "'JetBrains Mono', monospace",
        }}>
          Loading {symbol}...
        </div>
      )}

      {error && !loading && (
        <div style={{
          position: 'absolute', inset: 0, display: 'flex', alignItems: 'center',
          justifyContent: 'center', fontSize: 11, color: 'var(--text-muted)',
          background: '#0a0a0f',
        }}>
          {error}
        </div>
      )}

      {tooltip && showCrosshair && (
        <div className="tv-tooltip">
          <span className="tv-label">O</span><span style={{ color: '#f0f0f5' }}>{tooltip.open}</span>{'  '}
          <span className="tv-label">H</span><span style={{ color: '#34c759' }}>{tooltip.high}</span>{'  '}
          <span className="tv-label">L</span><span style={{ color: '#ff453a' }}>{tooltip.low}</span>{'  '}
          <span className="tv-label">C</span>
          <span style={{ color: tooltip.isUp ? '#34c759' : '#ff453a' }}>{tooltip.close}</span>
        </div>
      )}
    </div>
  )
}
