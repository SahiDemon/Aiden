import React, { useState, useEffect } from 'react'
import { Fan, Power, PowerOff, RefreshCw, Wifi, WifiOff } from 'lucide-react'
import { toast } from 'react-hot-toast'
import { Button } from '../ui/button'
import { Badge } from '../ui/badge'
import api from '../../lib/api'

const SmartDeviceCard = ({ connected, deviceUpdates, compact = false }) => {
  const [deviceStatus, setDeviceStatus] = useState(null)
  const [loading, setLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState(null)

  useEffect(() => {
    // Fetch status once on mount
    fetchDeviceStatus()
    
    // Don't poll constantly - only fetch when needed
    // WebSocket will handle real-time updates
  }, [])

  const fetchDeviceStatus = async () => {
    try {
      setLoading(true)
      const data = await api.getESP32Status()
      setDeviceStatus(data)
    } catch (error) {
      console.error('Error fetching device status:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleControl = async (action) => {
    // Prevent multiple clicks - return if already loading
    if (actionLoading) {
      console.log('Action already in progress, ignoring click')
      return
    }

    if (!connected || !deviceStatus?.connected) {
      toast.error('Device not connected')
      return
    }

    setActionLoading(action)
    
    try {
      console.log(`Sending single command: ${action}`)
      const result = await api.controlESP32(action)
      
      if (result.success) {
        toast.success(result.message || `Fan ${action} successful`)
        // Don't fetch status after control - WebSocket will update
        // This prevents constant polling that causes the fan to turn on/off repeatedly
      } else {
        toast.error(result.message || 'Control failed')
      }
    } catch (error) {
      toast.error('Failed to control device')
      console.error('Control error:', error)
    } finally {
      setActionLoading(null)
    }
  }

  const isDeviceConnected = deviceStatus?.connected
  const deviceState = deviceStatus?.status

  if (compact) {
    return (
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium text-blue-200/80 flex items-center gap-2">
            <Fan className="w-4 h-4 text-blue-300" />
            Smart Fan
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
            variant={isDeviceConnected ? "default" : "destructive"}
            className={`text-xs px-2 py-0.5 ${isDeviceConnected ? 'bg-blue-500/20 border-blue-400/30 text-blue-200' : ''}`}
          >
            {isDeviceConnected ? 'Online' : 'Offline'}
          </Badge>
        </div>

        {isDeviceConnected && deviceState && (
          <div className="flex items-center justify-between text-xs">
            <span className="text-white/70">State</span>
            <span className="text-blue-200 capitalize">
              {deviceState.state || 'Unknown'}
            </span>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="liquid-glass-card p-6">
      <div className="pb-3 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-white flex items-center gap-2">
          <Fan className="w-5 h-5" />
          Smart Fan
        </h2>
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
        {/* Connection Status */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm">
            {isDeviceConnected ? (
              <Wifi className="w-4 h-4 text-emerald-400" />
            ) : (
              <WifiOff className="w-4 h-4 text-red-400" />
            )}
            <span className="text-white/70">
              {deviceStatus?.ip_address || '192.168.1.180'}
            </span>
          </div>
          <Badge 
            variant={isDeviceConnected ? "default" : "destructive"}
            className="bg-white/10 border-white/20 text-white"
          >
            {isDeviceConnected ? 'Connected' : 'Offline'}
          </Badge>
        </div>

        {/* Device State */}
        {isDeviceConnected && deviceState && (
          <>
            <div className="h-px bg-white/10" />
            
            <div className="flex items-center justify-between p-3 bg-white/5 border border-white/10">
              <div>
                <p className="text-sm font-medium text-white/80">Current State</p>
                <p className="text-xs text-white/60 capitalize">
                  {deviceState.state || 'Unknown'}
                  {deviceState.speed && ` • Speed: ${deviceState.speed}`}
                </p>
              </div>
              <Fan
                className={`w-6 h-6 ${
                  deviceState.state === 'on' ? 'text-emerald-400 animate-spin' : 'text-white/50'
                }`}
              />
            </div>
          </>
        )}

        <div className="h-px bg-white/10" />

        {/* Controls */}
        <div className="grid grid-cols-2 gap-2">
          <Button
            onClick={() => handleControl('turn_on')}
            disabled={!isDeviceConnected || actionLoading !== null}
            className="bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-400/30 text-emerald-300"
          >
            {actionLoading === 'turn_on' ? (
              <RefreshCw className="w-4 h-4 animate-spin mr-2" />
            ) : (
              <Power className="w-4 h-4 mr-2" />
            )}
            Turn On
          </Button>

          <Button
            onClick={() => handleControl('turn_off')}
            disabled={!isDeviceConnected || actionLoading !== null}
            className="bg-red-500/20 hover:bg-red-500/30 border border-red-400/30 text-red-300"
          >
            {actionLoading === 'turn_off' ? (
              <RefreshCw className="w-4 h-4 animate-spin mr-2" />
            ) : (
              <PowerOff className="w-4 h-4 mr-2" />
            )}
            Turn Off
          </Button>

          <Button
            onClick={() => handleControl('change_mode')}
            disabled={!isDeviceConnected || actionLoading !== null}
            className="col-span-2 bg-white/10 hover:bg-white/20 border border-white/20 text-white/80"
          >
            {actionLoading === 'change_mode' ? (
              <RefreshCw className="w-4 h-4 animate-spin mr-2" />
            ) : (
              <RefreshCw className="w-4 h-4 mr-2" />
            )}
            Change Mode
          </Button>
        </div>

        <p className="text-xs text-white/50 text-center">
          Voice: "turn on the fan" or "change fan mode"
        </p>
      </div>
    </div>
  )
}

export default SmartDeviceCard



