import React, { useState, useEffect, useRef, lazy, Suspense } from 'react'
import { MessageSquare, Waves, Plus, History, Settings, Activity, Monitor, X, Check } from 'lucide-react'
import { Toaster, toast } from 'react-hot-toast'
import ChatInterface from './components/chat/ChatInterface'
import TimerDisplay from './components/TimerDisplay'
import SystemStats from './components/system/SystemStats'
import SmartDeviceCard from './components/smart-home/SmartDeviceCard'
import useWebSocket from './hooks/useWebSocket'
import api from './lib/api'
const SettingsDialog = lazy(() => import('./components/settings/SettingsDialog'))
const ConversationHistory = lazy(() => import('./components/chat/ConversationHistory'))

function App() {
  const [mode, setMode] = useState('chat')
  const [panel, setPanel] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const [messages, setMessages] = useState([])
  const [timers, setTimers] = useState([])
  const [resetting, setResetting] = useState(false)
  const [busy, setBusy] = useState(false)
  const [session, setSession] = useState(0)
  const seen = useRef(0)
  const { connected, messages: incoming, voiceActivity, systemMetrics, deviceUpdates, speakingText,
    timerUpdates, audioBlocked, audioError, unlockAudio, resumeAudio, audioEnabled, toggleAudio, sendMessage } = useWebSocket()
  useEffect(() => {
    const fresh = incoming.slice(seen.current)
    seen.current = incoming.length
    if (fresh.length) setMessages(previous => {
      const next = [...previous]
      fresh.filter(message => message.role !== 'action').forEach(message => {
        const index = message.client_message_id ? next.findIndex(existing => existing.client_message_id === message.client_message_id && existing.role === message.role) : -1
        if (index >= 0) next[index] = { ...next[index], ...message, delivery: 'sent' }
        else next.push(message)
      })
      return next
    })
  }, [incoming])
  const addOutgoing = (id, content) => setMessages(previous => [...previous, { role: 'user', content, client_message_id: id, timestamp: new Date().toISOString(), delivery: 'sending' }])
  const completeOutgoing = (id, response, failed = false) => setMessages(previous => {
    const next = previous.map(message => message.client_message_id === id && message.role === 'user' ? { ...message, delivery: failed ? 'failed' : 'sent' } : message)
    if (response && !next.some(message => message.client_message_id === id && message.role === 'assistant')) next.push({ role: 'assistant', content: response, client_message_id: id, timestamp: new Date().toISOString() })
    return next
  })
  const refreshTimers = async () => {
    try { const result = await api.getActiveTimers(); if (result.success) setTimers(result.timers || []) }
    catch { /* Refresh on the next server event. */ }
  }
  useEffect(() => { if (connected) refreshTimers() }, [connected, timerUpdates])
  const newConversation = async () => {
    setResetting(true)
    try {
      await api.newConversation()
      seen.current = incoming.length
      setMessages([]); setSession(value => value + 1); setMode('chat'); toast.success('New conversation ready')
    } catch (error) { toast.error(error.message || 'Could not start a conversation') }
    finally { setResetting(false) }
  }
  const selectConversation = async conversation => {
    if (busy || ['processing', 'listening', 'speaking'].includes(voiceActivity?.status)) {
      toast.error('Wait for Aiden to finish the current request')
      return
    }
    try {
      const result = await api.resumeConversation(conversation.id)
      setMessages(result.messages || result.conversation?.messages || [])
      setSession(value => value + 1); setMode('chat')
    } catch (error) { toast.error(error.message) }
  }
  const working = busy || ['processing', 'listening', 'speaking'].includes(voiceActivity?.status)
  return (
    <div className="aiden-app">
      <a className="skip-link" href="#conversation">Skip to conversation</a>
      <Toaster position="top-center" toastOptions={{ className: 'aiden-toast', duration: 2800, success: { icon: <Check size={18} className="toast-success-icon" aria-hidden="true" /> }, error: { icon: <X size={18} className="toast-error-icon" aria-hidden="true" /> }, style: { background: 'var(--panel-bg)', color: 'var(--ink)', border: '1px solid var(--theme-line)' } }} />
      <aside className="workspace-nav" aria-label="Workspace">
        <a className="brand" href="#conversation"><span className="brand-symbol">a</span><span>aiden<span className="brand-caption">YOUR PERSONAL ASSISTANT</span></span></a>
        <button className="new-chat" onClick={newConversation} disabled={!connected || resetting || working} title={!connected ? 'Connect your PC to start a conversation' : working ? 'Wait for the current reply to finish' : 'Start a new conversation'}><Plus size={18} />{resetting ? 'Starting…' : 'New conversation'}<span>↗</span></button>
        <p className="nav-label">Workspace</p>
        <nav>
          <button className={mode === 'chat' ? 'selected' : ''} onClick={() => setMode('chat')}><MessageSquare size={18} />Conversation</button>
          <button className={mode === 'voice' ? 'selected' : ''} onClick={() => setMode('voice')}><Waves size={18} />Voice studio<span className="nav-tag">LIVE</span></button>
          <button onClick={() => setShowHistory(true)}><History size={18} />History</button>
          <button className={panel ? 'selected' : ''} onClick={() => setPanel(!panel)} aria-expanded={panel}><Activity size={18} />PC & devices</button>
        </nav>
        <div className="nav-note"><span className="small-wave">∿</span><p>A little less clicking.<br />A little more doing.</p></div>
        <div className="nav-footer"><div className="host-connection"><Monitor size={18} /><div>Your computer<small><i className={connected ? 'status-dot online' : 'status-dot'} />{connected ? 'Connected to Aiden' : 'Waiting for connection'}</small></div></div><button onClick={() => setShowSettings(true)}><Settings size={18} />Settings</button></div>
      </aside>
      <div className="workspace-main">
        <header className="workspace-header"><div><span className="mobile-brand">aiden / </span>{mode === 'voice' ? 'Voice studio' : 'Conversation'}<span className="header-divider">/</span><span className="header-muted">Your everyday, assisted</span></div><div className="header-actions"><span className={`connection-pill ${connected ? 'connected' : ''}`}><i className="status-dot" />{connected ? 'PC connected' : 'PC offline'}</span><button className={`icon-button ${panel ? 'selected' : ''}`} aria-label="Toggle PC and devices" aria-expanded={panel} onClick={() => setPanel(!panel)}><Activity size={19} /></button></div></header>
        <main id="conversation" className="conversation-workspace"><ChatInterface key={session} messages={messages} connected={connected} voiceActivity={voiceActivity} speakingText={speakingText} mode={mode} setMode={setMode} onBusyChange={setBusy} onOutgoing={addOutgoing} onCompleted={completeOutgoing} audioBlocked={audioBlocked} audioError={audioError} unlockAudio={unlockAudio} resumeAudio={resumeAudio} audioEnabled={audioEnabled} toggleAudio={toggleAudio} sendMessage={sendMessage} /></main>
        <nav className="mobile-nav" aria-label="Mobile workspace"><button className={mode === 'chat' ? 'selected' : ''} onClick={() => setMode('chat')}><MessageSquare size={20} />Chat</button><button className={mode === 'voice' ? 'selected' : ''} onClick={() => setMode('voice')}><Waves size={20} />Voice</button><button onClick={newConversation} disabled={!connected || working || resetting}><Plus size={20} />New</button><button onClick={() => setShowHistory(true)}><History size={20} />History</button><button onClick={() => setShowSettings(true)}><Settings size={20} />Settings</button></nav>
      </div>
      {panel && <aside className="device-panel" aria-label="PC and devices"><div className="panel-heading"><div><p className="eyebrow">CONNECTED WORKSPACE</p><h2>PC & smart home</h2></div><button className="icon-button" aria-label="Close PC and devices" onClick={() => setPanel(false)}><X size={20} /></button></div><p className="panel-description">Live readings. A little more control.</p><SystemStats connected={connected} systemMetrics={systemMetrics} /><SmartDeviceCard connected={connected} deviceUpdates={deviceUpdates} /><div className="remote-note"><Monitor size={20} /><p>Here or on your phone.<small>Your requests run on this PC. Voice replies play on the device you’re using.</small></p></div></aside>}
      <Suspense fallback={<div className="dialog-loading" role="status">Opening…</div>}>{showSettings && <SettingsDialog open={showSettings} onOpenChange={setShowSettings} />}{showHistory && <ConversationHistory isOpen={showHistory} onClose={() => setShowHistory(false)} onSelectConversation={selectConversation} />}</Suspense>
      <TimerDisplay timers={timers} onTimerUpdate={refreshTimers} />
    </div>
  )
}
export default App
