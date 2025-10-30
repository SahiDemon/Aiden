import React from 'react'
import { Brain, Sparkles } from 'lucide-react'
import { Label } from '../ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select'
import { Slider } from '../ui/slider'
import { Input } from '../ui/input'
import { Separator } from '../ui/separator'

const AISettings = ({ settings, onChange }) => {
  const groqModels = [
    { value: 'llama-3.1-8b-instant', label: 'Llama 3.1 8B (Instant)' },
    { value: 'llama-3.1-70b-versatile', label: 'Llama 3.1 70B (Versatile)' },
    { value: 'llama-3.2-1b-preview', label: 'Llama 3.2 1B (Preview)' },
    { value: 'llama-3.2-3b-preview', label: 'Llama 3.2 3B (Preview)' },
    { value: 'mixtral-8x7b-32768', label: 'Mixtral 8x7B' },
    { value: 'gemma-7b-it', label: 'Gemma 7B' },
  ]

  return (
    <div className="space-y-6">
      {/* Model Settings */}
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <Brain className="w-4 h-4" />
          <h3 className="font-semibold">Groq AI Configuration</h3>
        </div>

        <div className="space-y-3">
          <div className="space-y-2">
            <Label>Model</Label>
            <Select
              value={settings.model}
              onValueChange={(value) => onChange('model', value)}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select model" />
              </SelectTrigger>
              <SelectContent>
                {groqModels.map(model => (
                  <SelectItem key={model.value} value={model.value}>
                    {model.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Llama 3.1 8B is recommended for speed
            </p>
          </div>

          <div className="space-y-2">
            <div className="flex justify-between">
              <Label>Temperature</Label>
              <span className="text-sm text-muted-foreground">
                {settings.temperature?.toFixed(1) || 0.3}
              </span>
            </div>
            <Slider
              value={[settings.temperature || 0.3]}
              onValueChange={([value]) => onChange('temperature', value)}
              min={0}
              max={1}
              step={0.1}
              className="w-full"
            />
            <p className="text-xs text-muted-foreground">
              Lower = more focused, higher = more creative
            </p>
          </div>

          <div className="space-y-2">
            <div className="flex justify-between">
              <Label>Max Tokens</Label>
              <span className="text-sm text-muted-foreground">
                {settings.max_tokens || 500}
              </span>
            </div>
            <Slider
              value={[settings.max_tokens || 500]}
              onValueChange={([value]) => onChange('max_tokens', value)}
              min={100}
              max={2000}
              step={100}
              className="w-full"
            />
            <p className="text-xs text-muted-foreground">
              Maximum length of AI responses
            </p>
          </div>
        </div>
      </div>

      <Separator />

      {/* User Settings */}
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4" />
          <h3 className="font-semibold">Personalization</h3>
        </div>

        <div className="space-y-3">
          <div className="space-y-2">
            <Label>Your Name</Label>
            <Input
              value={settings.user_name || ''}
              onChange={(e) => onChange('user_name', e.target.value)}
              placeholder="Boss"
            />
            <p className="text-xs text-muted-foreground">
              How Aiden should address you
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

export default AISettings



