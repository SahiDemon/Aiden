import React, { useEffect, useMemo, useState } from 'react'
import { Brain, KeyRound, RefreshCw, Save, Search, Settings2, SlidersHorizontal } from 'lucide-react'
import { toast } from 'react-hot-toast'

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Textarea } from '../ui/textarea'
import { Label } from '../ui/label'
import { Switch } from '../ui/switch'
import { Badge } from '../ui/badge'
import { ScrollArea } from '../ui/scroll-area'
import { Separator } from '../ui/separator'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select'
import api from '../../lib/api'

const sections = [
  { id: 'overview', label: 'Overview' },
  { id: 'ai', label: 'AI & Models' },
  { id: 'prompts', label: 'Prompts' },
  { id: 'speech', label: 'Speech' },
  { id: 'wake', label: 'Wake Word' },
  { id: 'system', label: 'System' },
  { id: 'auto_shutdown', label: 'Auto Shutdown' },
  { id: 'esp32', label: 'ESP32' },
  { id: 'spotify', label: 'Spotify' },
  { id: 'cache', label: 'Cache' },
  { id: 'infra', label: 'Infra' },
  { id: 'ups', label: 'UPS' },
]

const secretFields = new Set([
  'gemini.api_key',
  'gemini.api_key_1',
  'gemini.api_key_2',
  'gemini.api_key_3',
  'groq.api_key',
  'spotify.client_id',
  'spotify.client_secret',
  'spotify.refresh_token',
  'speech.google_tts_credentials_path',
  'speech.porcupine_access_key',
])

const providerConfigKey = {
  gemini: 'gemini',
  groq: 'groq',
  ollama: 'ollama',
}

const clone = (value) => JSON.parse(JSON.stringify(value))

const setIn = (object, path, value) => {
  const next = clone(object)
  const parts = path.split('.')
  let current = next
  for (let i = 0; i < parts.length - 1; i += 1) {
    current[parts[i]] = current[parts[i]] || {}
    current = current[parts[i]]
  }
  current[parts[parts.length - 1]] = value
  return next
}

const getIn = (object, path, fallback = '') => {
  return path.split('.').reduce((acc, key) => (acc && acc[key] !== undefined ? acc[key] : undefined), object) ?? fallback
}

const SettingRow = ({ label, hint, children }) => (
  <div className="space-y-2 border-b border-white/5 pb-4">
    <div className="flex flex-col md:flex-row md:items-center justify-between gap-2 md:gap-6">
      <div className="max-w-md">
        <Label className="text-sm font-medium text-white">{label}</Label>
        {hint && <p className="mt-1 text-xs text-white/45">{hint}</p>}
      </div>
      <div className="w-full max-w-xl">{children}</div>
    </div>
  </div>
)

const SecretInput = ({ value, onChange, placeholder }) => (
  <Input
    value={value || ''}
    onChange={(event) => onChange(event.target.value)}
    placeholder={placeholder}
    className="border-white/10 bg-white/5 text-white"
  />
)

const TextInput = ({ value, onChange, type = 'text', placeholder }) => (
  <Input
    type={type}
    value={value ?? ''}
    onChange={(event) => onChange(type === 'number' ? Number(event.target.value) : event.target.value)}
    placeholder={placeholder}
    className="border-white/10 bg-white/5 text-white"
  />
)

const SettingsDialog = ({ open, onOpenChange }) => {
  const [settings, setSettings] = useState(null)
  const [savedSettings, setSavedSettings] = useState(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [activeSection, setActiveSection] = useState('overview')
  const [search, setSearch] = useState('')
  const [providerModels, setProviderModels] = useState({})
  const [providerStatus, setProviderStatus] = useState({})

  const hasChanges = useMemo(
    () => settings && savedSettings && JSON.stringify(settings) !== JSON.stringify(savedSettings),
    [settings, savedSettings]
  )

  useEffect(() => {
    if (open) {
      void fetchSettings()
    }
  }, [open])

  useEffect(() => {
    const provider = settings?.app?.llm_provider
    if (provider) {
      void refreshModels(provider)
    }
  }, [settings?.app?.llm_provider, settings?.ollama?.base_url])

  const fetchSettings = async () => {
    try {
      setLoading(true)
      const response = await api.getSettings()
      setSettings(response.settings)
      setSavedSettings(response.settings)
      setProviderModels(response.settings?.model_options || {})
    } catch (error) {
      toast.error('Failed to load settings')
    } finally {
      setLoading(false)
    }
  }

  const refreshModels = async (provider) => {
    try {
      const response = await api.getProviderModels(provider)
      setProviderStatus((prev) => ({
        ...prev,
        [provider]: response,
      }))
      if (response.models) {
        setProviderModels((prev) => ({
          ...prev,
          [provider]: response.models,
        }))
      }
    } catch (error) {
      setProviderStatus((prev) => ({
        ...prev,
        [provider]: { reachable: false, error: error.message, models: [] },
      }))
    }
  }

  const updateField = (path, value) => {
    setSettings((prev) => setIn(prev, path, value))
  }

  const handleSave = async () => {
    if (!hasChanges) return
    try {
      setSaving(true)
      const response = await api.updateSettings(settings)
      setSettings(response.settings)
      setSavedSettings(response.settings)
      toast.success('Settings saved')
    } catch (error) {
      toast.error(error.message || 'Failed to save settings')
    } finally {
      setSaving(false)
    }
  }

  const filteredSections = sections.filter((section) =>
    section.label.toLowerCase().includes(search.toLowerCase())
  )

  const currentProvider = settings?.app?.llm_provider || 'gemini'
  const currentProviderKey = providerConfigKey[currentProvider]
  const currentProviderModels = providerModels[currentProvider] || []
  const currentProviderStatus = providerStatus[currentProvider]

  if (!open) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="!block h-[95vh] max-h-[95vh] max-w-[96vw] overflow-hidden border-white/10 bg-slate-950 p-0 text-white shadow-2xl">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,_rgba(59,130,246,0.18),_transparent_28%),radial-gradient(circle_at_bottom_right,_rgba(14,165,233,0.15),_transparent_32%)]" />
        <div className="relative flex h-full flex-col">
          <DialogHeader className="border-b border-white/10 px-4 py-3 md:px-8 md:py-5 bg-white/[0.02]">
            <div className="flex flex-row items-center justify-between gap-2 md:gap-6">
              <div className="min-w-0 flex-1 hidden md:block">
                <DialogTitle className="flex items-center gap-2 md:gap-3 text-base md:text-2xl font-bold tracking-tight text-white truncate">
                  <Settings2 className="h-4 w-4 md:h-6 md:w-6 text-sky-300 shrink-0" />
                  <span>Aiden Settings Console</span>
                </DialogTitle>
                <DialogDescription className="mt-1 hidden md:block max-w-3xl text-xs md:text-sm text-white/55">
                  Provider switching, detected models, prompts, speech, integrations, and runtime controls are managed here from one real settings contract.
                </DialogDescription>
              </div>
              <div className="md:hidden min-w-0 flex-1 pr-2">
                <Select value={activeSection} onValueChange={setActiveSection}>
                  <SelectTrigger className="h-9 border-white/10 bg-white/5 text-white w-full rounded-xl">
                    <SelectValue placeholder="Select section" />
                  </SelectTrigger>
                  <SelectContent>
                    {sections.map((section) => (
                      <SelectItem key={section.id} value={section.id}>
                        {section.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <Badge className="hidden sm:inline-flex border-sky-400/20 bg-sky-400/10 text-sky-200 text-xs">
                  Provider: {currentProvider}
                </Badge>
                {hasChanges && <Badge className="border-amber-400/20 bg-amber-400/10 text-amber-200 text-xs px-2 py-0.5">Unsaved</Badge>}
                <Button variant="outline" size="sm" onClick={fetchSettings} className="h-9 w-9 md:w-auto md:px-2.5 px-0 text-xs border-white/10 bg-white/5 text-white hover:bg-white/10 flex justify-center items-center rounded-xl">
                  <RefreshCw className="h-4 w-4 md:h-3.5 md:w-3.5 md:mr-1.5" />
                  <span className="hidden md:inline">Reload</span>
                </Button>
                <Button size="sm" onClick={handleSave} disabled={!hasChanges || saving} className="h-9 md:px-3 px-3 text-xs bg-sky-500 text-slate-950 font-semibold hover:bg-sky-400 flex justify-center items-center rounded-xl">
                  <Save className="h-4 w-4 md:h-3.5 md:w-3.5 md:mr-1.5" />
                  <span className="hidden md:inline">{saving ? 'Saving...' : 'Save'}</span>
                </Button>
              </div>
            </div>
          </DialogHeader>

          <div className="flex flex-col md:grid min-h-0 flex-1 md:grid-cols-[240px_minmax(0,1fr)_320px] overflow-hidden">
            {/* Desktop Left Sidebar */}
            <aside className="hidden md:block border-r border-white/10 bg-white/[0.02] p-4 flex-shrink-0">
              <div className="relative mb-4">
                <Search className="absolute left-3 top-3 h-4 w-4 text-white/35" />
                <Input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search sections"
                  className="border-white/10 bg-white/5 pl-9 text-white"
                />
              </div>
              <ScrollArea className="h-[calc(95vh-180px)] pr-3">
                <div className="flex flex-col space-y-1">
                  {filteredSections.map((section) => (
                    <button
                      key={section.id}
                      type="button"
                      onClick={() => setActiveSection(section.id)}
                      className={`whitespace-nowrap rounded-xl px-4 py-2 text-left text-sm transition ${activeSection === section.id ? 'bg-sky-400/15 text-sky-200 font-medium' : 'text-white/65 hover:bg-white/5 hover:text-white'}`}
                    >
                      {section.label}
                    </button>
                  ))}
                </div>
              </ScrollArea>
            </aside>

            <div className="h-full min-h-0 overflow-y-auto px-4 md:px-8 py-4 md:py-6">
              {loading || !settings ? (
                <div className="flex h-full items-center justify-center text-white/55">Loading settings...</div>
              ) : (
                <div className="space-y-8 pb-24">
                  {activeSection === 'overview' && (
                    <>
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                          <div className="text-xs uppercase tracking-[0.2em] text-white/35">LLM</div>
                          <div className="mt-3 text-xl font-semibold">{currentProvider}</div>
                          <div className="mt-1 text-sm text-white/45">
                            {getIn(settings, `${currentProviderKey}.model`, 'No model selected')}
                          </div>
                        </div>
                        <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                          <div className="text-xs uppercase tracking-[0.2em] text-white/35">Gemini Keys</div>
                          <div className="mt-3 text-xl font-semibold">{settings.meta?.gemini?.configured_key_count || 0}</div>
                          <div className="mt-1 text-sm text-white/45">
                            Rotation {settings.meta?.gemini?.rotation_enabled ? 'enabled' : 'disabled'}
                          </div>
                        </div>
                        <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                          <div className="text-xs uppercase tracking-[0.2em] text-white/35">Detected Models</div>
                          <div className="mt-3 text-xl font-semibold">{currentProviderModels.length}</div>
                          <div className="mt-1 text-sm text-white/45">
                            {currentProviderStatus?.reachable === false ? 'Provider unreachable' : 'Live provider options'}
                          </div>
                        </div>
                      </div>
                    </>
                  )}

                  {activeSection === 'ai' && (
                    <>
                      <div className="space-y-5">
                        <SettingRow label="Provider" hint="Switch between Gemini, Groq, and Ollama.">
                          <Select value={currentProvider} onValueChange={(value) => updateField('app.llm_provider', value)}>
                            <SelectTrigger className="border-white/10 bg-white/5 text-white">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="gemini">Gemini</SelectItem>
                              <SelectItem value="groq">Groq</SelectItem>
                              <SelectItem value="ollama">Ollama</SelectItem>
                            </SelectContent>
                          </Select>
                        </SettingRow>

                        {currentProvider === 'ollama' && (
                          <SettingRow label="Ollama Base URL" hint="Changing the base URL refreshes detected model options.">
                            <TextInput value={settings.ollama.base_url} onChange={(value) => updateField('ollama.base_url', value)} placeholder="http://localhost:11434" />
                          </SettingRow>
                        )}

                        <SettingRow label="Model" hint="Options are provider-specific and loaded from the backend.">
                          <div className="space-y-3">
                            <div className="flex gap-3">
                              <div className="flex-1">
                                <Select value={getIn(settings, `${currentProviderKey}.model`, '')} onValueChange={(value) => updateField(`${currentProviderKey}.model`, value)}>
                                  <SelectTrigger className="border-white/10 bg-white/5 text-white">
                                    <SelectValue placeholder="Select model" />
                                  </SelectTrigger>
                                  <SelectContent>
                                    {currentProviderModels.map((model) => (
                                      <SelectItem key={model.value} value={model.value}>
                                        {model.label}
                                      </SelectItem>
                                    ))}
                                  </SelectContent>
                                </Select>
                              </div>
                              <Button variant="outline" onClick={() => refreshModels(currentProvider)} className="border-white/10 bg-white/5 text-white hover:bg-white/10">
                                <RefreshCw className="mr-2 h-4 w-4" />
                                Detect
                              </Button>
                            </div>
                            {currentProviderStatus?.reachable === false && (
                              <p className="text-xs text-rose-300">{currentProviderStatus.error || 'Provider is not reachable right now.'}</p>
                            )}
                          </div>
                        </SettingRow>

                        <SettingRow label="Temperature">
                          <TextInput type="number" value={getIn(settings, `${currentProviderKey}.temperature`, 0)} onChange={(value) => updateField(`${currentProviderKey}.temperature`, value)} />
                        </SettingRow>
                        <SettingRow label="Max Tokens">
                          <TextInput type="number" value={getIn(settings, `${currentProviderKey}.max_tokens`, 0)} onChange={(value) => updateField(`${currentProviderKey}.max_tokens`, value)} />
                        </SettingRow>

                        <Separator className="bg-white/10" />

                        <div className="space-y-4">
                          <div className="flex items-center gap-2 text-sm font-semibold text-white">
                            <KeyRound className="h-4 w-4 text-sky-300" />
                            Provider Secrets
                          </div>
                          {['gemini.api_key', 'gemini.api_key_1', 'gemini.api_key_2', 'gemini.api_key_3', 'groq.api_key'].map((path) => (
                            <SettingRow key={path} label={path.replace('.', ' ').toUpperCase()} hint="Encrypted in stored overrides.">
                              <SecretInput value={getIn(settings, path, '')} onChange={(value) => updateField(path, value)} placeholder="Enter secret" />
                            </SettingRow>
                          ))}
                        </div>
                      </div>
                    </>
                  )}

                  {activeSection === 'prompts' && (
                    <div className="space-y-5">
                      {Object.entries(settings.prompts || {}).map(([key, value]) => (
                        <SettingRow key={key} label={key} hint="Prompt overrides persist in the database and apply at runtime.">
                          <Textarea
                            value={value}
                            onChange={(event) => updateField(`prompts.${key}`, event.target.value)}
                            className="min-h-[220px] border-white/10 bg-white/5 text-white"
                          />
                        </SettingRow>
                      ))}
                    </div>
                  )}

                  {activeSection === 'speech' && (
                    <div className="space-y-5">
                      {['speech.tts_provider', 'speech.tts_voice', 'speech.tts_rate', 'speech.google_tts_voice', 'speech.google_tts_pitch', 'speech.google_tts_speaking_rate', 'speech.google_tts_credentials_path', 'speech.stt_language', 'speech.stt_timeout', 'speech.stt_pause_threshold', 'speech.stt_non_speaking_duration', 'speech.stt_device_index', 'speech.stt_energy_threshold'].map((path) => (
                        <SettingRow key={path} label={path.split('.').slice(1).join('_')}>
                          {secretFields.has(path) ? (
                            <SecretInput value={getIn(settings, path, '')} onChange={(value) => updateField(path, value)} placeholder="Enter value" />
                          ) : (
                            <TextInput value={getIn(settings, path, '')} onChange={(value) => updateField(path, value)} placeholder="Enter value" />
                          )}
                        </SettingRow>
                      ))}
                    </div>
                  )}

                  {activeSection === 'wake' && (
                    <div className="space-y-5">
                      {['speech.use_porcupine', 'speech.porcupine_access_key', 'speech.porcupine_model_path', 'speech.porcupine_sensitivity', 'speech.porcupine_min_energy', 'speech.porcupine_debounce_seconds', 'speech.porcupine_confirmation_window', 'speech.vosk_model_path'].map((path) => (
                        <SettingRow key={path} label={path.split('.').slice(1).join('_')}>
                          {typeof getIn(settings, path) === 'boolean' ? (
                            <div className="flex justify-end"><Switch checked={getIn(settings, path, false)} onCheckedChange={(value) => updateField(path, value)} /></div>
                          ) : secretFields.has(path) ? (
                            <SecretInput value={getIn(settings, path, '')} onChange={(value) => updateField(path, value)} placeholder="Enter value" />
                          ) : (
                            <TextInput value={getIn(settings, path, '')} onChange={(value) => updateField(path, value)} placeholder="Enter value" />
                          )}
                        </SettingRow>
                      ))}
                    </div>
                  )}

                  {activeSection === 'system' && (
                    <div className="space-y-5">
                      {['app.name', 'app.user_name', 'app.wake_word', 'app.hotkey', 'app.toggle_hotkey', 'app.debug', 'app.enable_enhanced_responses'].map((path) => (
                        <SettingRow key={path} label={path.split('.').slice(1).join('_')}>
                          {typeof getIn(settings, path) === 'boolean' ? (
                            <div className="flex justify-end"><Switch checked={getIn(settings, path, false)} onCheckedChange={(value) => updateField(path, value)} /></div>
                          ) : typeof getIn(settings, path) === 'number' ? (
                            <TextInput type="number" value={getIn(settings, path, 0)} onChange={(value) => updateField(path, value)} />
                          ) : (
                            <TextInput value={getIn(settings, path, '')} onChange={(value) => updateField(path, value)} placeholder="Enter value" />
                          )}
                        </SettingRow>
                      ))}
                    </div>
                  )}

                  {activeSection === 'auto_shutdown' && (
                    <div className="space-y-5">
                      <SettingRow label="Enable Auto Shutdown" hint="Initiates system shutdown if PC is idle and no media is playing">
                        <div className="flex justify-end">
                          <Switch
                            checked={getIn(settings, 'app.media_idle_shutdown_enabled', false)}
                            onCheckedChange={(value) => updateField('app.media_idle_shutdown_enabled', value)}
                          />
                        </div>
                      </SettingRow>
                      <SettingRow label="Auto Shutdown Timeout (Minutes)" hint="Minutes of inactivity before automatic shutdown triggers">
                        <TextInput
                          type="number"
                          value={getIn(settings, 'app.media_idle_timeout_minutes', 15)}
                          onChange={(value) => updateField('app.media_idle_timeout_minutes', value)}
                        />
                      </SettingRow>
                    </div>
                  )}

                  {['esp32', 'spotify', 'cache', 'ups'].includes(activeSection) && (
                    <div className="space-y-5">
                      {Object.keys(settings[activeSection] || {}).map((key) => {
                        const path = `${activeSection}.${key}`
                        const value = getIn(settings, path)
                        return (
                          <SettingRow key={path} label={key}>
                            {typeof value === 'boolean' ? (
                              <div className="flex justify-end"><Switch checked={value} onCheckedChange={(checked) => updateField(path, checked)} /></div>
                            ) : secretFields.has(path) ? (
                              <SecretInput value={value || ''} onChange={(next) => updateField(path, next)} placeholder="Enter value" />
                            ) : (
                              <TextInput value={value ?? ''} onChange={(next) => updateField(path, next)} placeholder="Enter value" />
                            )}
                          </SettingRow>
                        )
                      })}
                    </div>
                  )}

                  {activeSection === 'infra' && (
                    <div className="space-y-5">
                      {['api.host', 'api.port', 'api.reload', 'database.database_url', 'database.pool_size', 'database.max_overflow', 'database.pool_timeout', 'redis.url', 'redis.socket_timeout', 'redis.socket_connect_timeout'].map((path) => (
                        <SettingRow key={path} label={path}>
                          {typeof getIn(settings, path) === 'boolean' ? (
                            <div className="flex justify-end"><Switch checked={getIn(settings, path, false)} onCheckedChange={(checked) => updateField(path, checked)} /></div>
                          ) : (
                            <TextInput value={getIn(settings, path, '')} onChange={(value) => updateField(path, value)} placeholder="Enter value" />
                          )}
                        </SettingRow>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>

            <aside className="h-full overflow-y-auto border-t md:border-l border-white/10 bg-white/[0.03] px-6 py-6 hidden md:block">
              <div className="space-y-6">
                <div>
                  <div className="flex items-center gap-2 text-sm font-semibold text-white">
                    <Brain className="h-4 w-4 text-sky-300" />
                    Provider Health
                  </div>
                  <p className="mt-2 text-sm text-white/50">
                    Current provider: <span className="text-white">{currentProvider}</span>
                  </p>
                  <p className="mt-1 text-sm text-white/50">
                    Current model: <span className="text-white">{getIn(settings, `${currentProviderKey}.model`, 'None')}</span>
                  </p>
                  <p className="mt-1 text-sm text-white/50">
                    Reachable: <span className="text-white">{currentProviderStatus?.reachable === false ? 'No' : 'Yes'}</span>
                  </p>
                </div>

                <Separator className="bg-white/10" />

                <div>
                  <div className="flex items-center gap-2 text-sm font-semibold text-white">
                    <SlidersHorizontal className="h-4 w-4 text-sky-300" />
                    Notes
                  </div>
                  <ul className="mt-3 space-y-2 text-sm text-white/50">
                    <li>Model options are backend-driven.</li>
                    <li>Gemini keeps automatic key rotation.</li>
                    <li>Prompt overrides apply without editing YAML directly.</li>
                    <li>Masked secrets are preserved unless you replace them.</li>
                  </ul>
                </div>
              </div>
            </aside>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

export default SettingsDialog
