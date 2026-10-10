import React, { useEffect, useState } from 'react'
import { Cpu, HardDrive, Monitor, ArrowUpRight } from 'lucide-react'
import api from '../../lib/api'

function Metric({ label, value, icon: Icon }) {
  const known = typeof value === 'number' && Number.isFinite(value)
  const percent = known ? Math.min(100, Math.max(0, value)) : 0
  return <div className={`pc-metric ${known && value >= 90 ? 'under-pressure' : ''}`}>
    <div className="metric-caption"><Icon size={15} /><span>{label}</span></div>
    <div className="metric-number">{known ? value.toFixed(1) : '—'}{known && <span>%</span>}</div>
    <div className="metric-track" role="meter" aria-label={`${label} usage`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={known ? percent : undefined} aria-valuetext={known ? `${value.toFixed(1)} percent` : 'Waiting for data'}><span style={{ transform: `scaleX(${percent / 100})` }} /></div>
    <small>{!known ? 'Waiting for data' : value >= 90 ? 'High usage' : label === 'CPU' ? 'Processor usage' : 'Memory in use'}</small>
  </div>
}

export default function SystemStats({ connected, systemMetrics, compact = false }) {
  const [stats, setStats] = useState(null)
  const [health, setHealth] = useState(null)
  const [error, setError] = useState(false)
  useEffect(() => {
    if (!connected) return
    let active = true
    const fetchStats = async () => {
      try {
        const [status, services] = await Promise.all([api.getSystemStatus(), api.getHealth()])
        if (active) { setStats(status); setHealth(services); setError(false) }
      } catch { if (active) setError(true) }
    }
    fetchStats()
    const interval = setInterval(fetchStats, 5000)
    return () => { active = false; clearInterval(interval) }
  }, [connected])
  const metrics = connected ? systemMetrics || stats : null
  const services = Object.entries(health?.services || {})
  const healthy = services.filter(([, value]) => value === true).length
  return <section className={`pc-overview ${compact ? 'compact' : ''}`} aria-label="Computer status">
    <div className="section-topline"><span className="section-kicker">YOUR COMPUTER</span><span className={`panel-live ${connected ? 'is-online' : ''}`}><i />{connected ? 'Live' : 'Offline'}</span></div>
    <div className="pc-title"><Monitor size={19} /><h2>System overview</h2></div>
    {!connected && <p className="panel-feedback">Connect to Aiden to see live readings.</p>}
    {error && connected && <p className="panel-feedback" role="status">Status refresh failed. Showing the latest available readings.</p>}
    <div className="pc-metrics"><Metric label="CPU" value={metrics?.system?.cpu_percent} icon={Cpu} /><Metric label="RAM" value={metrics?.system?.memory_percent} icon={HardDrive} /></div>
    <details className="system-details"><summary><span>Services & cache</span><span>{connected && services.length ? `${healthy}/${services.length} healthy` : 'Details'}<ArrowUpRight size={13} /></span></summary><div className="service-list">{services.length ? services.map(([name, value]) => <div key={name}><span>{name}</span><span className={connected && value === true ? 'service-healthy' : 'service-unavailable'}><i />{!connected ? 'Offline' : value === true ? 'Healthy' : 'Unavailable'}</span></div>) : <p className="panel-feedback">Waiting for service status.</p>}</div>{metrics?.cache && <dl className="cache-details"><div><dt>Cached items</dt><dd>{metrics.cache.total_keys ?? '—'}</dd></div><div><dt>Cache hit rate</dt><dd>{typeof metrics.cache.hit_rate === 'number' ? `${metrics.cache.hit_rate.toFixed(1)}%` : '—'}</dd></div></dl>}</details>
  </section>
}
