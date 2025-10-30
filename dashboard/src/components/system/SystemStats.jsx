import React, { useState, useEffect } from 'react'
import { Activity, Cpu, Database, HardDrive, Wifi, WifiOff } from 'lucide-react'
import { Badge } from '../ui/badge'
import api from '../../lib/api'

const SystemStats = ({ connected, systemMetrics, compact = false }) => {
  const [stats, setStats] = useState(null)
  const [health, setHealth] = useState(null)

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const [statsData, healthData] = await Promise.all([
          api.getSystemStatus(),
          api.getHealth()
        ])
        setStats(statsData)
        setHealth(healthData)
      } catch (error) {
        console.error('Error fetching stats:', error)
      }
    }

    if (connected) {
      fetchStats()
      const interval = setInterval(fetchStats, 5000)
      return () => clearInterval(interval)
    }
  }, [connected])

  // Use WebSocket metrics if available, otherwise use polled stats
  const currentMetrics = systemMetrics || stats

  if (compact) {
    return (
      <div className="space-y-3">
        <h3 className="text-sm font-medium text-blue-200/80 flex items-center gap-2">
          <Activity className="w-4 h-4 text-blue-300" />
          System Status
        </h3>
        
        {/* Connection Status */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {connected ? (
              <Wifi className="w-3 h-3 text-blue-400" />
            ) : (
              <WifiOff className="w-3 h-3 text-red-400" />
            )}
            <span className="text-xs text-white/70">Connection</span>
          </div>
          <Badge 
            variant={connected ? "default" : "destructive"}
            className={`text-xs px-2 py-0.5 ${connected ? 'bg-blue-500/20 border-blue-400/30 text-blue-200' : ''}`}
          >
            {connected ? 'Online' : 'Offline'}
          </Badge>
        </div>

        {/* Compact System Metrics */}
        {currentMetrics && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="text-white/70">CPU</span>
              <span className="font-mono text-blue-200">
                {currentMetrics.system?.cpu_percent?.toFixed(1) || 0}%
              </span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-white/70">Memory</span>
              <span className="font-mono text-blue-200">
                {currentMetrics.system?.memory_percent?.toFixed(1) || 0}%
              </span>
            </div>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="liquid-glass-card p-6">
      <div className="pb-3">
        <h2 className="text-lg font-semibold text-white flex items-center gap-2">
          <Activity className="w-5 h-5" />
          System Status
        </h2>
      </div>
      
      <div className="space-y-4">
        {/* Connection Status */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {connected ? (
              <Wifi className="w-4 h-4 text-emerald-400" />
            ) : (
              <WifiOff className="w-4 h-4 text-red-400" />
            )}
            <span className="text-sm font-medium text-white/80">Connection</span>
          </div>
          <Badge 
            variant={connected ? "default" : "destructive"}
            className="bg-white/10 border-white/20 text-white"
          >
            {connected ? 'Online' : 'Offline'}
          </Badge>
        </div>

        <div className="h-px bg-white/10" />

        {/* System Metrics */}
        {currentMetrics && (
          <>
            <div className="space-y-3">
              {/* CPU */}
              <div className="space-y-1">
                <div className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-2">
                    <Cpu className="w-4 h-4 text-blue-400" />
                    <span className="text-white/80">CPU</span>
                  </div>
                  <span className="font-mono text-xs text-white/90">
                    {currentMetrics.system?.cpu_percent?.toFixed(1) || 0}%
                  </span>
                </div>
                <div className="h-2 bg-white/10 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-blue-500 to-blue-400 transition-all duration-300"
                    style={{ width: `${currentMetrics.system?.cpu_percent || 0}%` }}
                  />
                </div>
              </div>

              {/* Memory */}
              <div className="space-y-1">
                <div className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-2">
                    <HardDrive className="w-4 h-4 text-emerald-400" />
                    <span className="text-white/80">Memory</span>
                  </div>
                  <span className="font-mono text-xs text-white/90">
                    {currentMetrics.system?.memory_percent?.toFixed(1) || 0}%
                  </span>
                </div>
                <div className="h-2 bg-white/10 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-emerald-500 to-emerald-400 transition-all duration-300"
                    style={{ width: `${currentMetrics.system?.memory_percent || 0}%` }}
                  />
                </div>
              </div>
            </div>

            <div className="h-px bg-white/10" />

            {/* Cache Stats */}
            {currentMetrics.cache && (
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-sm font-medium text-white/80">
                  <Database className="w-4 h-4" />
                  <span>Cache</span>
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="space-y-1">
                    <p className="text-white/60">Keys</p>
                    <p className="font-mono text-white/90">{currentMetrics.cache.total_keys || 0}</p>
                  </div>
                  <div className="space-y-1">
                    <p className="text-white/60">Hit Rate</p>
                    <p className="font-mono text-white/90">
                      {currentMetrics.cache.hit_rate?.toFixed(1) || 0}%
                    </p>
                  </div>
                </div>
              </div>
            )}
          </>
        )}

        <div className="h-px bg-white/10" />

        {/* Services Health */}
        {health && (
          <div className="space-y-2">
            <p className="text-sm font-medium text-white/80">Services</p>
            <div className="grid grid-cols-2 gap-2">
              {Object.entries(health.services || {}).map(([service, isHealthy]) => (
                <div key={service} className="flex items-center gap-2 text-xs">
                  <div className={`w-2 h-2 rounded-full ${isHealthy ? 'bg-emerald-400' : 'bg-red-400'}`} />
                  <span className="capitalize text-white/70">{service}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default SystemStats



