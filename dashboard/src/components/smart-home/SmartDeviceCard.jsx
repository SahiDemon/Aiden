import React, { useEffect, useMemo, useState } from 'react'
import { Fan, RefreshCw, Wifi, WifiOff } from 'lucide-react'
import { toast } from 'react-hot-toast'
import { Button } from '../ui/button'
import { Badge } from '../ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select'
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
  const summary = device?.summary || deviceStatus?.status || {}
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

    if (!connected || !isDeviceConnected) {
      toast.error('Device not connected')
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

  const renderStepButtons = (control, columns = 2) => (
    <div className={`grid gap-2 ${columns === 3 ? 'grid-cols-3' : 'grid-cols-2'}`}>
      {control.steps.map((step) => {
        const isActive = control.value === step.key
        const loadingKey = `${control.id}:${step.key}`
        return (
          <Button
            key={`${control.id}-${step.key}`}
            onClick={() => handleControl(control.id, { target: step.key })}
            disabled={!isDeviceConnected || actionLoading !== null}
            className={
              isActive
                ? 'bg-blue-500/20 border border-blue-400/40 text-blue-100 hover:bg-blue-500/25'
                : 'bg-white/5 border border-white/10 text-white/75 hover:bg-white/10'
            }
          >
            {actionLoading === loadingKey ? (
              <RefreshCw className="w-4 h-4 animate-spin mr-2" />
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
    const usesSelect = control.kind === 'cycle' && steps.length > 5

    return (
      <div key={control.id} className="rounded-xl border border-white/10 bg-white/5 p-3 space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-sm font-medium text-white/85">{control.label}</p>
            <p className="text-xs text-white/50">
              {control.value_label || control.value || 'Unknown'}
            </p>
          </div>
          <Badge className="bg-white/10 border-white/10 text-white/80">
            {control.feature}
          </Badge>
        </div>

        {usesSelect ? (
          <Select
            value={control.value || ''}
            onValueChange={(value) => handleControl(control.id, { target: value })}
          >
            <SelectTrigger
              className="border-white/10 bg-white/5 text-white"
              disabled={!isDeviceConnected || actionLoading !== null}
            >
              <SelectValue placeholder={`Select ${control.label.toLowerCase()}`} />
            </SelectTrigger>
            <SelectContent className="border-white/10 bg-slate-950 text-white">
              {steps.map((step) => (
                <SelectItem key={`${control.id}-${step.key}`} value={step.key} className="text-white">
                  {step.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : isToggle ? (
          renderStepButtons(control, 2)
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
            <Fan className={`w-4 h-4 ${summary.state === 'on' ? 'text-emerald-300' : 'text-blue-300'}`} />
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
              <Wifi className="w-3 h-3 text-blue-400" />
            ) : (
              <WifiOff className="w-3 h-3 text-red-400" />
            )}
            <span className="text-xs text-white/70">Device</span>
          </div>
          <Badge
            variant={isDeviceConnected ? 'default' : 'destructive'}
            className={isDeviceConnected ? 'text-xs px-2 py-0.5 bg-blue-500/20 border-blue-400/30 text-blue-200' : 'text-xs px-2 py-0.5'}
          >
            {isDeviceConnected ? 'Online' : 'Offline'}
          </Badge>
        </div>

        {quickFacts.length > 0 && (
          <p className="text-xs text-white/60 leading-relaxed">
            {quickFacts.join(' • ')}
          </p>
        )}
      </div>
    )
  }

  return (
    <div className="liquid-glass-card p-6">
      <div className="pb-3 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white flex items-center gap-2">
            <Fan className={`w-5 h-5 ${summary.state === 'on' ? 'text-emerald-300 animate-spin' : ''}`} />
            {device?.device_name || 'Smart Fan'}
          </h2>
          <p className="text-xs text-white/50 mt-1">
            Runtime controls from the ESP32 device
          </p>
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

      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm">
            {isDeviceConnected ? (
              <Wifi className="w-4 h-4 text-emerald-400" />
            ) : (
              <WifiOff className="w-4 h-4 text-red-400" />
            )}
            <span className="text-white/70">{deviceStatus?.ip_address || '192.168.1.180'}</span>
          </div>
          <Badge
            variant={isDeviceConnected ? 'default' : 'destructive'}
            className="bg-white/10 border-white/20 text-white"
          >
            {isDeviceConnected ? 'Connected' : 'Offline'}
          </Badge>
        </div>

        <div className="rounded-xl border border-white/10 bg-white/5 p-3">
          <p className="text-sm font-medium text-white/80">Current Runtime State</p>
          <p className="text-xs text-white/60 mt-1">
            {quickFacts.length > 0 ? quickFacts.join(' • ') : 'No live state available'}
          </p>
        </div>

        <div className="space-y-3">
          {controls.length > 0 ? (
            controls.map(renderControl)
          ) : (
            <div className="rounded-xl border border-dashed border-white/10 bg-white/5 p-4 text-sm text-white/60">
              {isDeviceConnected
                ? 'No runtime controls were returned by the ESP32.'
                : 'ESP32 fan is offline. Once it reconnects, the live controls will appear here.'}
            </div>
          )}
        </div>

        <p className="text-xs text-white/50 text-center">
          Voice: “set fan timer to 3.5 hours”, “set speed to 2”, or “turn oscillation on”
        </p>
      </div>
    </div>
  )
}

export default SmartDeviceCard
