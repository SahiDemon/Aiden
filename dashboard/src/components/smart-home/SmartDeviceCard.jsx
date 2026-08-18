import React, { useEffect, useMemo, useState } from 'react'
import { Fan, RefreshCw, Wifi, WifiOff, Power, RotateCw, Clock, Gauge, Zap } from 'lucide-react'
import { toast } from 'react-hot-toast'
import { Button } from '../ui/button'
import { Badge } from '../ui/badge'
import api from '../../lib/api'

const SmartDeviceCard = ({ connected, deviceUpdates, compact = false }) => {
  const [deviceStatus, setDeviceStatus] = useState(null)
  const [loading, setLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState(null)

  const fetchDeviceStatus = async () => {
    try {
      setLoading(true)
      const data = await api.getESP32Device()
      setDeviceStatus(data)
    } catch (error) {
      console.error('Error fetching ESP32 device payload:', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchDeviceStatus()

    const interval = setInterval(() => {
      fetchDeviceStatus()
    }, 15000)

    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    const payload = deviceUpdates?.data
    if (!payload) return

    if (payload.device) {
      setDeviceStatus((prev) => ({
        ...(prev || {}),
        success: true,
        connected: payload.connected ?? prev?.connected ?? false,
        ip_address: payload.device.ip_address || prev?.ip_address,
        device: payload.device,
        status: payload.device.summary || prev?.status,
      }))
      return
    }

    fetchDeviceStatus()
  }, [deviceUpdates])

  const isDeviceConnected = deviceStatus?.connected
  const device = deviceStatus?.device
  const summary = useMemo(
    () => device?.summary || deviceStatus?.status || {},
    [device?.summary, deviceStatus?.status]
  )
  const controls = device?.controls || []

  const quickFacts = useMemo(() => {
    const parts = []
    if (summary.state) parts.push(`Power ${summary.state}`)
    if (summary.speed) parts.push(`Speed ${summary.speed}`)
    if (summary.timer) parts.push(`Timer ${summary.timer}`)
    if (summary.mode) parts.push(`Mode ${summary.mode}`)
    return parts
  }, [summary])

  const handleControl = async (controlId, payload) => {
    if (actionLoading) {
      return
    }

    if (!connected) {
      toast.error('Not connected to Aiden')
      return
    }

    const loadingKey = `${controlId}:${payload.target || payload.action || 'set'}`
    setActionLoading(loadingKey)

    try {
      const result = await api.controlESP32({
        control_id: controlId,
        ...payload,
      })

      if (result.success) {
        if (result.device) {
          setDeviceStatus((prev) => ({
            ...(prev || {}),
            success: true,
            connected: result.connected ?? prev?.connected ?? true,
            ip_address: result.device.ip_address || prev?.ip_address,
            device: result.device,
            status: result.device.summary || prev?.status,
          }))
        } else {
          fetchDeviceStatus()
        }
        toast.success(result.message || `${controlId} updated`)
      } else {
        toast.error(result.message || 'Control failed')
      }
    } catch (error) {
      toast.error(error.message || 'Failed to control device')
      console.error('ESP32 control error:', error)
    } finally {
      setActionLoading(null)
    }
  }

  // Default fallback controls when backend controls list is not populated yet
  const defaultControls = useMemo(() => [
    {
      id: 'power',
      label: 'Fan Power',
      feature: 'Power',
      kind: 'toggle',
      value: summary.state || 'off',
      steps: [
        { key: 'on', label: 'Power ON' },
        { key: 'off', label: 'Power OFF' },
      ],
    },
    {
      id: 'oscillation',
      label: 'Rotate / Oscillation',
      feature: 'Swing',
      kind: 'toggle',
      value: summary.oscillation || summary.mode || 'off',
      steps: [
        { key: 'on', label: 'Rotate ON' },
        { key: 'off', label: 'Rotate OFF' },
      ],
    },
    {
      id: 'speed',
      label: 'Fan Speed Level',
      feature: 'Speed',
      kind: 'step',
      value: String(summary.speed || '1'),
      steps: [
        { key: '1', label: 'Speed 1' },
        { key: '2', label: 'Speed 2' },
        { key: '3', label: 'Speed 3' },
        { key: '4', label: 'Speed 4' },
        { key: '5', label: 'Speed 5' },
      ],
    },
    {
      id: 'timer',
      label: 'Shutdown Timer',
      feature: 'Timer',
      kind: 'step',
      value: summary.timer ? String(summary.timer) : 'off',
      steps: [
        { key: 'off', label: 'Off' },
        { key: '1h', label: '1 Hour' },
        { key: '2h', label: '2 Hours' },
        { key: '4h', label: '4 Hours' },
        { key: '8h', label: '8 Hours' },
      ],
    },
  ], [summary])

  const activeControls = controls.length > 0 ? controls : defaultControls

  const getControlIcon = (feature) => {
    switch (String(feature || '').toLowerCase()) {
      case 'power': return <Power className="w-4 h-4 text-emerald-400" />
      case 'swing':
      case 'oscillation': return <RotateCw className="w-4 h-4 text-sky-400" />
      case 'speed': return <Gauge className="w-4 h-4 text-blue-400" />
      case 'timer': return <Clock className="w-4 h-4 text-purple-400" />
      default: return <Zap className="w-4 h-4 text-amber-400" />
    }
  }

  const renderStepButtons = (control, columns = 2) => (
    <div className={`grid gap-2 ${columns === 5 ? 'grid-cols-5' : columns === 4 ? 'grid-cols-4' : columns === 3 ? 'grid-cols-3' : 'grid-cols-2'}`}>
      {control.steps.map((step) => {
        const isActive = String(control.value) === String(step.key)
        const loadingKey = `${control.id}:${step.key}`
        return (
          <Button
            key={`${control.id}-${step.key}`}
            onClick={() => handleControl(control.id, { target: step.key })}
            disabled={actionLoading !== null}
            className={
              isActive
                ? 'bg-blue-500/25 border border-blue-400/50 text-blue-100 font-semibold shadow-md shadow-blue-500/10 hover:bg-blue-500/35 transition-all text-xs py-1.5 h-auto'
                : 'bg-white/5 border border-white/10 text-white/75 hover:bg-white/10 hover:text-white transition-all text-xs py-1.5 h-auto'
            }
          >
            {actionLoading === loadingKey ? (
              <RefreshCw className="w-3 h-3 animate-spin mr-1" />
            ) : null}
            {step.label}
          </Button>
        )
      })}
    </div>
  )

  const renderControl = (control) => {
    const steps = control.steps || []
    const isToggle = control.kind === 'toggle' || steps.length === 2
    const isSpeedOrTimer = control.id === 'speed' || control.id === 'timer'

    return (
      <div key={control.id} className="rounded-xl border border-white/10 bg-white/5 p-3 space-y-2.5 backdrop-blur-sm">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            {getControlIcon(control.feature || control.id)}
            <p className="text-sm font-medium text-white/90">{control.label}</p>
          </div>
          <Badge className="bg-white/10 border-white/10 text-white/80 text-[10px]">
            {control.feature || control.id}
          </Badge>
        </div>

        {isToggle ? (
          renderStepButtons(control, 2)
        ) : isSpeedOrTimer ? (
          renderStepButtons(control, steps.length)
        ) : (
          renderStepButtons(control, steps.length >= 3 ? 3 : 2)
        )}
      </div>
    )
  }

  if (compact) {
    return (
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium text-blue-200/80 flex items-center gap-2">
            <Fan className={`w-4 h-4 ${summary.state === 'on' ? 'text-emerald-300 animate-spin' : 'text-blue-300'}`} />
            {device?.device_name || 'Smart Fan'}
          </h3>
          <Button
            size="sm"
            variant="ghost"
            onClick={fetchDeviceStatus}
            disabled={loading}
            className="h-6 w-6 p-0 text-blue-200/70 hover:text-blue-200 hover:bg-blue-500/10"
          >
            <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {isDeviceConnected ? (
              <Wifi className="w-3 h-3 text-emerald-400" />
            ) : (
              <WifiOff className="w-3 h-3 text-red-400" />
            )}
            <span className="text-xs text-white/70">{deviceStatus?.ip_address || '192.168.1.180'}</span>
          </div>
          <Badge
            variant={isDeviceConnected ? 'default' : 'destructive'}
            className={isDeviceConnected ? 'text-xs px-2 py-0.5 bg-emerald-500/20 border-emerald-400/30 text-emerald-200' : 'text-xs px-2 py-0.5'}
          >
            {isDeviceConnected ? 'Connected' : 'Offline'}
          </Badge>
        </div>

        {/* Compact Quick Controls */}
        <div className="grid grid-cols-2 gap-1.5">
          <Button
            size="sm"
            onClick={() => handleControl('power', { target: summary.state === 'on' ? 'off' : 'on' })}
            className={`h-8 text-xs ${summary.state === 'on' ? 'bg-emerald-500/20 border border-emerald-400/40 text-emerald-200' : 'bg-white/5 border border-white/10 text-white/70'}`}
          >
            <Power className="w-3 h-3 mr-1.5" />
            {summary.state === 'on' ? 'Fan ON' : 'Fan OFF'}
          </Button>
          <Button
            size="sm"
            onClick={() => handleControl('oscillation', { target: summary.oscillation === 'on' ? 'off' : 'on' })}
            className={`h-8 text-xs ${summary.oscillation === 'on' ? 'bg-sky-500/20 border border-sky-400/40 text-sky-200' : 'bg-white/5 border border-white/10 text-white/70'}`}
          >
            <RotateCw className="w-3 h-3 mr-1.5" />
            {summary.oscillation === 'on' ? 'Rotate ON' : 'Rotate OFF'}
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="liquid-glass-card p-5 md:p-6">
      <div className="pb-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-bold text-white flex items-center gap-2.5">
            <Fan className={`w-5 h-5 ${summary.state === 'on' ? 'text-emerald-400 animate-spin' : 'text-blue-400'}`} />
            {device?.device_name || 'Smart Fan Control'}
          </h2>
          <Badge
            variant={isDeviceConnected ? 'default' : 'destructive'}
            className={isDeviceConnected ? 'bg-emerald-500/20 border-emerald-400/30 text-emerald-200 text-xs' : 'bg-red-500/20 border-red-400/30 text-red-200 text-xs'}
          >
            {isDeviceConnected ? 'Online' : 'Offline'}
          </Badge>
        </div>
        <Button
          size="icon"
          variant="ghost"
          onClick={fetchDeviceStatus}
          disabled={loading}
          className="h-8 w-8 text-white/70 hover:text-white hover:bg-white/10"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </Button>
      </div>

      <div className="space-y-4 pt-2">
        <div className="rounded-xl border border-white/10 bg-white/5 p-3">
          <p className="text-sm font-medium text-white/80">Current Runtime State</p>
          <p className="mt-1 text-xs text-white/60">
            {quickFacts.length > 0 ? quickFacts.join(' • ') : 'No live state available'}
          </p>
        </div>

        {/* Interactive Controls List */}
        <div className="space-y-3">
          {activeControls.map(renderControl)}
        </div>
      </div>
    </div>
  )
}
export default SmartDeviceCard
