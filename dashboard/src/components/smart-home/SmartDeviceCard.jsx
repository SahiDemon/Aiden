import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Fan, RefreshCw, Power, RotateCw, Clock, Gauge, Sliders } from 'lucide-react'
import { toast } from 'react-hot-toast'
import api from '../../lib/api'

const fallbackControls = summary => [
  { id: 'power', label: 'Power', kind: 'toggle', value: summary.state, steps: [{ key: 'off', label: 'Off' }, { key: 'on', label: 'On' }] },
  { id: 'speed', label: 'Speed', value: summary.speed, steps: ['1', '2', '3', '4', '5'].map(key => ({ key, label: `Speed ${key}` })) },
  { id: 'timer', label: 'Turn off after', value: summary.timer, steps: [{ key: 'off', label: 'Timer off' }, ...['1h', '2h', '4h', '8h'].map(key => ({ key, label: key }))] },
  { id: 'oscillation', label: 'Oscillation', kind: 'toggle', value: summary.oscillation, steps: [{ key: 'off', label: 'Off' }, { key: 'on', label: 'On' }] },
]
const controlIcon = id => /power/i.test(id) ? Power : /speed/i.test(id) ? Gauge : /timer/i.test(id) ? Clock : /osc|swing|rotation/i.test(id) ? RotateCw : Sliders

export default function SmartDeviceCard({ connected, deviceUpdates, compact = false }) {
  const [snapshot, setSnapshot] = useState(null)
  const [loading, setLoading] = useState(false)
  const [pending, setPending] = useState(null)
  const [feedback, setFeedback] = useState(null)
  const mounted = useRef(false)
  const pendingRef = useRef(false)
  const revision = useRef(0)
  const fetchStatus = useCallback(async () => {
    const version = revision.current
    setLoading(true)
    try {
      const data = await api.getESP32Device()
      if (mounted.current && version === revision.current) { setSnapshot(data); setFeedback(null) }
    } catch {
      if (mounted.current) setFeedback({ error: true, text: 'Could not refresh device status. Try again.' })
    } finally { if (mounted.current) setLoading(false) }
  }, [])
  useEffect(() => {
    mounted.current = true
    if (connected) fetchStatus()
    const interval = connected ? setInterval(fetchStatus, 15000) : null
    return () => { mounted.current = false; clearInterval(interval) }
  }, [connected, fetchStatus])
  useEffect(() => {
    const payload = deviceUpdates?.data
    if (!payload) return
    if (payload.device) {
      revision.current += 1
      setSnapshot(previous => ({ ...previous, connected: payload.connected ?? previous?.connected ?? false, device: payload.device, status: payload.device.summary }))
    } else if (connected) fetchStatus()
  }, [deviceUpdates, connected, fetchStatus])
  const device = snapshot?.device
  const summary = device?.summary || snapshot?.status || {}
  const online = connected && snapshot?.connected === true
  const controls = device?.controls?.length ? device.controls : fallbackControls(summary)
  const powered = String(controls.find(control => control.id === 'power')?.value || summary.state).toLowerCase() === 'on'
  const runControl = async (control, target) => {
    if (!online || pendingRef.current) return
    pendingRef.current = true
    revision.current += 1
    setPending(control.id); setFeedback(null)
    try {
      const result = await api.controlESP32({ control_id: control.id, target })
      if (!result.success) throw new Error(result.message || 'The device did not accept this change.')
      if (!mounted.current) return
      if (result.device) setSnapshot(previous => ({ ...previous, connected: result.connected ?? previous?.connected, device: result.device, status: result.device.summary }))
      else await fetchStatus()
      const text = result.message || `${control.label} updated`
      setFeedback({ error: false, text }); toast.success(text)
    } catch (error) {
      if (mounted.current) { setFeedback({ error: true, text: error.message || 'Control failed. Try again.' }); toast.error(error.message || 'Control failed') }
    } finally {
      pendingRef.current = false
      if (mounted.current) setPending(null)
    }
  }
  const renderControl = control => {
    const Icon = controlIcon(control.feature || control.id)
    const steps = control.steps || []
    const current = steps.find(step => String(step.key) === String(control.value))
    const isTimer = /timer/i.test(`${control.id} ${control.feature}`)
    const isToggle = control.kind === 'toggle' && steps.length === 2
    const onStep = steps.find(step => String(step.key).toLowerCase() === 'on')
    const offStep = steps.find(step => String(step.key).toLowerCase() === 'off')
    const switchable = isToggle && onStep && offStep
    const disabled = !online || pending !== null
    const enabled = String(control.value) === String(onStep?.key)
    return <div className={`device-control ${isTimer ? 'timer-control' : ''}`} key={control.id}>
      <div className="control-heading"><div><Icon size={16} /><label htmlFor={`device-${control.id}`}>{isTimer ? 'Turn off after' : control.label}</label></div><span>{pending === control.id ? 'Updating…' : current?.label || '—'}</span></div>
      {switchable ? <button id={`device-${control.id}`} className={`device-switch ${enabled ? 'on' : ''}`} role="switch" aria-checked={enabled} aria-label={control.label} disabled={disabled} onClick={() => runControl(control, enabled ? offStep.key : onStep.key)}><span /></button> : isTimer || steps.length > 5 ? <select id={`device-${control.id}`} aria-label={isTimer ? 'Turn off after' : control.label} value={current ? String(control.value) : ''} disabled={disabled} onChange={event => runControl(control, event.target.value)}><option value="" disabled>Choose {isTimer ? 'a duration' : 'an option'}</option>{steps.map(step => <option key={step.key} value={String(step.key)}>{step.label}</option>)}</select> : <div className="device-segments" role="group" aria-label={control.label}>{steps.map(step => <button key={step.key} aria-pressed={String(control.value) === String(step.key)} disabled={disabled} onClick={() => runControl(control, step.key)}>{pending === control.id && String(control.value) === String(step.key) ? <RefreshCw size={13} className="control-spinning" /> : null}{step.label}</button>)}</div>}
    </div>
  }
  return <section className={`smart-device ${compact ? 'compact' : ''}`} aria-label="Smart home device">
    <div className="section-topline"><span className="section-kicker">SMART HOME</span><button className="device-refresh" aria-label="Refresh device status" onClick={fetchStatus} disabled={loading || !connected || pending !== null}><RefreshCw size={15} className={loading ? 'control-spinning' : ''} /></button></div>
    <div className="fan-intro"><div className={`fan-emblem ${powered && online ? 'running' : ''}`}><Fan size={32} /></div><div><h2>{device?.device_name || 'Smart fan'}</h2><p><span className={`panel-live ${online ? 'is-online' : ''}`}><i />{online ? 'Connected' : loading ? 'Connecting…' : 'Offline'}</span></p></div></div>
    <div className="fan-state"><span>{online ? powered ? 'Power on' : 'Power off' : 'Device unavailable'}</span><small>{online ? summary.speed ? `Speed ${summary.speed}` : 'Ready to control' : 'Connect your PC and device'}</small></div>
    {feedback && <p className={`device-feedback ${feedback.error ? 'failed' : ''}`} role={feedback.error ? 'alert' : 'status'}>{feedback.text}</p>}
    <div className="device-controls" aria-busy={pending !== null}>{controls.filter(control => !compact || /power|osc|swing/i.test(control.id)).map(renderControl)}</div>
    <div className="device-footnote"><i className={`status-dot ${online ? 'online' : ''}`} />{pending ? 'Sending to your device' : online ? 'Changes apply to your device immediately' : 'Controls become available when connected'}</div>
  </section>
}
