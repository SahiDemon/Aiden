import React from 'react'
import { Settings2, Wifi, Volume } from 'lucide-react'
import { Label } from '../ui/label'
import { Input } from '../ui/input'
import { Switch } from '../ui/switch'
import { Separator } from '../ui/separator'

const SystemSettings = ({ settings, esp32Settings, onChange, onESP32Change }) => {
  return (
    <div className="space-y-6">
      {/* General Settings */}
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <Settings2 className="w-4 h-4" />
          <h3 className="font-semibold">General Settings</h3>
        </div>

        <div className="space-y-3">
          <div className="space-y-2">
            <Label>Wake Word</Label>
            <Input
              value={settings.wake_word || 'aiden'}
              onChange={(e) => onChange('wake_word', e.target.value.toLowerCase())}
              placeholder="aiden"
            />
            <p className="text-xs text-muted-foreground">
              Word to activate voice assistant
            </p>
          </div>

          <div className="space-y-2">
            <Label>Hotkey</Label>
            <Input
              value={settings.hotkey || 'ctrl+shift+space'}
              onChange={(e) => onChange('hotkey', e.target.value)}
              placeholder="ctrl+shift+space"
            />
            <p className="text-xs text-muted-foreground">
              Keyboard shortcut for voice activation
            </p>
          </div>

          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>Debug Mode</Label>
              <p className="text-xs text-muted-foreground">
                Show detailed logs and information
              </p>
            </div>
            <Switch
              checked={settings.debug || false}
              onCheckedChange={(checked) => onChange('debug', checked)}
            />
          </div>
        </div>
      </div>

      <Separator />

      {/* Sound Settings */}
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <Volume className="w-4 h-4" />
          <h3 className="font-semibold">Sound Effects</h3>
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>Enable Sound Effects</Label>
              <p className="text-xs text-muted-foreground">
                Play sounds for activation, success, and errors
              </p>
            </div>
            <Switch
              checked={settings.enable_sound_effects !== false}
              onCheckedChange={(checked) => onChange('enable_sound_effects', checked)}
            />
          </div>
        </div>
      </div>

      <Separator />

      {/* ESP32 Smart Home */}
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <Wifi className="w-4 h-4" />
          <h3 className="font-semibold">Smart Home (ESP32)</h3>
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>Enable ESP32</Label>
              <p className="text-xs text-muted-foreground">
                Connect to ESP32 smart devices
              </p>
            </div>
            <Switch
              checked={esp32Settings?.enabled !== false}
              onCheckedChange={(checked) => onESP32Change('enabled', checked)}
            />
          </div>

          <div className="space-y-2">
            <Label>ESP32 IP Address</Label>
            <Input
              value={esp32Settings?.ip_address || '192.168.1.180'}
              onChange={(e) => onESP32Change('ip_address', e.target.value)}
              placeholder="192.168.1.180"
              disabled={esp32Settings?.enabled === false}
            />
            <p className="text-xs text-muted-foreground">
              Local IP address of your ESP32 device
            </p>
          </div>

          <div className="space-y-2">
            <Label>Connection Timeout (seconds)</Label>
            <Input
              type="number"
              value={esp32Settings?.timeout || 5}
              onChange={(e) => onESP32Change('timeout', parseInt(e.target.value))}
              min={1}
              max={30}
              disabled={esp32Settings?.enabled === false}
            />
            <p className="text-xs text-muted-foreground">
              How long to wait for device response
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

export default SystemSettings



