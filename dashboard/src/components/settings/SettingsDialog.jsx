import React, { useState, useEffect } from 'react'
import { Settings, Save, RotateCcw } from 'lucide-react'
import { toast } from 'react-hot-toast'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../ui/tabs'
import { Button } from '../ui/button'
import { ScrollArea } from '../ui/scroll-area'
import SpeechSettings from './SpeechSettings'
import AISettings from './AISettings'
import SystemSettings from './SystemSettings'
import api from '../../lib/api'

const SettingsDialog = ({ open, onOpenChange }) => {
  const [settings, setSettings] = useState(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [hasChanges, setHasChanges] = useState(false)
  const [activeTab, setActiveTab] = useState('speech')

  useEffect(() => {
    if (open) {
      fetchSettings()
    }
  }, [open])

  const fetchSettings = async () => {
    try {
      setLoading(true)
      const data = await api.getConfig()
      if (data.success) {
        setSettings(data.config)
        setHasChanges(false)
      }
    } catch (error) {
      toast.error('Failed to load settings')
      console.error('Settings fetch error:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async () => {
    if (!settings || !hasChanges) return

    setSaving(true)
    
    try {
      // Save each section separately
      const promises = []

      if (settings.speech) {
        promises.push(api.updateSpeechSettings(settings.speech))
      }

      if (settings.ai) {
        promises.push(api.updateAISettings(settings.ai))
      }

      if (settings.app) {
        promises.push(api.updateSystemSettings(settings.app))
      }

      await Promise.all(promises)
      
      toast.success('Settings saved successfully')
      setHasChanges(false)
    } catch (error) {
      toast.error('Failed to save settings')
      console.error('Settings save error:', error)
    } finally {
      setSaving(false)
    }
  }

  const handleReset = () => {
    if (window.confirm('Reset all settings to defaults? This cannot be undone.')) {
      fetchSettings()
      toast.success('Settings reset')
    }
  }

  const updateSettings = (section, key, value) => {
    setSettings(prev => ({
      ...prev,
      [section]: {
        ...prev[section],
        [key]: value
      }
    }))
    setHasChanges(true)
  }

  if (loading) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-3xl">
          <div className="flex items-center justify-center py-12">
            <p className="text-muted-foreground">Loading settings...</p>
          </div>
        </DialogContent>
      </Dialog>
    )
  }

  if (!settings) {
    return null
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[90vh]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Settings className="w-5 h-5" />
            Aiden Settings
          </DialogTitle>
          <DialogDescription>
            Configure speech, AI, system, and smart home settings
          </DialogDescription>
        </DialogHeader>

        {hasChanges && (
          <div className="bg-aiden-blue/10 border border-aiden-blue/30 rounded-md p-3 text-sm">
            You have unsaved changes. Click Save to apply them.
          </div>
        )}

        <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="speech">Speech</TabsTrigger>
            <TabsTrigger value="ai">AI</TabsTrigger>
            <TabsTrigger value="system">System</TabsTrigger>
          </TabsList>

          <ScrollArea className="h-[500px] mt-4">
            <TabsContent value="speech" className="space-y-4 pr-4">
              <SpeechSettings
                settings={settings.speech || {}}
                onChange={(key, value) => updateSettings('speech', key, value)}
              />
            </TabsContent>

            <TabsContent value="ai" className="space-y-4 pr-4">
              <AISettings
                settings={settings.groq || settings.ai || {}}
                onChange={(key, value) => updateSettings('groq', key, value)}
              />
            </TabsContent>

            <TabsContent value="system" className="space-y-4 pr-4">
              <SystemSettings
                settings={settings.app || {}}
                esp32Settings={settings.esp32 || {}}
                onChange={(key, value) => updateSettings('app', key, value)}
                onESP32Change={(key, value) => updateSettings('esp32', key, value)}
              />
            </TabsContent>
          </ScrollArea>
        </Tabs>

        <div className="flex items-center justify-between pt-4 border-t">
          <Button variant="outline" onClick={handleReset}>
            <RotateCcw className="w-4 h-4 mr-2" />
            Reset
          </Button>

          <Button
            onClick={handleSave}
            disabled={!hasChanges || saving}
          >
            {saving ? (
              <>
                <RotateCcw className="w-4 h-4 mr-2 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Save className="w-4 h-4 mr-2" />
                Save Changes
              </>
            )}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

export default SettingsDialog



