import React from 'react'
import { Volume2, Mic } from 'lucide-react'
import { Label } from '../ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'
import { Slider } from '../ui/slider'
import { Separator } from '../ui/separator'

const SpeechSettings = ({ settings, onChange }) => {
  const edgeTTSVoices = [
    { value: 'en-US-AvaNeural', label: 'Ava (Female)' },
    { value: 'en-US-AndrewNeural', label: 'Andrew (Male)' },
    { value: 'en-US-EmmaNeural', label: 'Emma (Female)' },
    { value: 'en-US-BrianNeural', label: 'Brian (Male)' },
    { value: 'en-US-JennyNeural', label: 'Jenny (Female)' },
    { value: 'en-US-GuyNeural', label: 'Guy (Male)' },
    { value: 'en-US-AriaNeural', label: 'Aria (Female)' },
    { value: 'en-US-DavisNeural', label: 'Davis (Male)' },
  ]

  return (
    <div className="space-y-6">
      {/* TTS Settings */}
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <Volume2 className="w-4 h-4" />
          <h3 className="font-semibold">Text-to-Speech</h3>
        </div>

        <div className="space-y-3">
          <div className="space-y-2">
            <Label>Voice</Label>
            <Select
              value={settings.tts_voice}
              onValueChange={(value) => onChange('tts_voice', value)}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select voice" />
              </SelectTrigger>
              <SelectContent>
                {edgeTTSVoices.map(voice => (
                  <SelectItem key={voice.value} value={voice.value}>
                    {voice.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <div className="flex justify-between">
              <Label>Speech Rate</Label>
              <span className="text-sm text-muted-foreground">
                {settings.tts_rate?.toFixed(1)}x
              </span>
            </div>
            <Slider
              value={[settings.tts_rate || 1.2]}
              onValueChange={([value]) => onChange('tts_rate', value)}
              min={0.5}
              max={2.0}
              step={0.1}
              className="w-full"
            />
            <p className="text-xs text-muted-foreground">
              Adjust how fast Aiden speaks
            </p>
          </div>
        </div>
      </div>

      <Separator />

      {/* STT Settings */}
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <Mic className="w-4 h-4" />
          <h3 className="font-semibold">Speech Recognition</h3>
        </div>

        <div className="space-y-3">
          <div className="space-y-2">
            <Label>Language</Label>
            <Select
              value={settings.stt_language}
              onValueChange={(value) => onChange('stt_language', value)}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select language" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="en-US">English (US)</SelectItem>
                <SelectItem value="en-GB">English (UK)</SelectItem>
                <SelectItem value="en-AU">English (AU)</SelectItem>
                <SelectItem value="en-CA">English (CA)</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <div className="flex justify-between">
              <Label>Timeout</Label>
              <span className="text-sm text-muted-foreground">
                {settings.stt_timeout || 10}s
              </span>
            </div>
            <Slider
              value={[settings.stt_timeout || 10]}
              onValueChange={([value]) => onChange('stt_timeout', value)}
              min={5}
              max={30}
              step={1}
              className="w-full"
            />
            <p className="text-xs text-muted-foreground">
              How long to wait for speech input
            </p>
          </div>

          <div className="space-y-2">
            <div className="flex justify-between">
              <Label>Energy Threshold</Label>
              <span className="text-sm text-muted-foreground">
                {settings.stt_energy_threshold || 600}
              </span>
            </div>
            <Slider
              value={[settings.stt_energy_threshold || 600]}
              onValueChange={([value]) => onChange('stt_energy_threshold', value)}
              min={200}
              max={2000}
              step={100}
              className="w-full"
            />
            <p className="text-xs text-muted-foreground">
              Microphone sensitivity (higher = less sensitive)
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

export default SpeechSettings



