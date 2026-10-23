import React, { useState, useEffect, useRef } from 'react'
import { Mic, MicOff, ArrowUp, Waves, MessageSquare, Monitor, Volume2, VolumeX, Globe, Music2, Command, ArrowUpRight, Copy, Check } from 'lucide-react'
import api from '../../lib/api'
import { useWebSpeech } from '../../hooks/useWebSpeech'
import WaveAnimation from './WaveAnimation'
const suggestions = [
  { icon: Command, title: 'Get something done', detail: 'Apps, reminders & everyday tasks', prompt: 'What can you help me do on my computer?' },
  { icon: Globe, title: 'Explore an idea', detail: 'Ask a question. Go a little deeper.', prompt: 'Help me explore an interesting idea about technology.' },
  { icon: Music2, title: 'Set the mood', detail: 'Find something good to listen to', prompt: 'Play some relaxing music on YouTube.' },
]
function ChatInterface({ messages = [], connected, voiceActivity, speakingText, mode = 'chat', setMode, onBusyChange, onOutgoing, onCompleted, audioBlocked, audioError, unlockAudio, resumeAudio, audioEnabled = true, toggleAudio, sendMessage }) {
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [interim, setInterim] = useState('')
  const [copied, setCopied] = useState(null)
  const [micSource, setMicSource] = useState('device')
  const endRef = useRef(null)
  const inputRef = useRef(null)
  const sendingRef = useRef(false)
  const voicePreviewRef = useRef(false)
  const voiceFinalRef = useRef(false)
  const publishPreview = (text, stage) => sendMessage?.('voice_transcript', { data: { text, stage } })
  const mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; if (voicePreviewRef.current && !voiceFinalRef.current) sendMessage?.('voice_transcript', { data: { text: '', stage: 'cancel' } }) } }, [sendMessage])
  const send = async (text, voice = false) => {
    if (!text.trim() || !connected || sendingRef.current) return
    const requestId = window.crypto?.randomUUID?.() || Date.now() + '-' + Math.random().toString(36).slice(2)
    onOutgoing?.(requestId, text.trim())
    setDraft('')
    sendingRef.current = true
    setSending(true); onBusyChange?.(true); setError(''); setInterim('')
    try {
      const result = await api.sendMessage(text.trim(), voice, requestId)
      if (result.success === false) throw new Error(result.message || 'The request failed')
      if (mounted.current) onCompleted?.(requestId, result.response)
    } catch (err) {
      if (mounted.current) { setError(err.message || 'Could not send. Try again.'); setDraft(current => current || text); onCompleted?.(requestId, null, true) }
    } finally {
      sendingRef.current = false
      if (mounted.current) { setSending(false); onBusyChange?.(false) }
    }
  }
  const { isSupported, isRecording, startRecording, stopRecording } = useWebSpeech({
    onStart: () => {
      voicePreviewRef.current = mode === 'voice'
      voiceFinalRef.current = false
      if (voicePreviewRef.current) publishPreview('', 'start')
    },
    onResult: (partial, final) => {
      setInterim(partial)
      if (voicePreviewRef.current) {
        publishPreview(final || partial, final ? 'final' : 'partial')
        if (final) voiceFinalRef.current = true
      }
      if (final) send(final, voicePreviewRef.current)
    },
    onEnd: () => {
      setInterim('')
      if (voicePreviewRef.current && !voiceFinalRef.current) publishPreview('', 'cancel')
      voicePreviewRef.current = false
    },
    onError: reason => setError(reason === 'not-allowed' ? 'Allow microphone access in your browser. On your phone, microphone access requires HTTPS.' : `Microphone: ${reason}. ${mode === 'voice' ? 'Try again or switch to Chat to type.' : 'You can still type a message.'}`),
  })
  const listening = isRecording || (mode === 'voice' && voiceActivity?.status === 'listening')
  const speaking = mode === 'voice' && (voiceActivity?.speaking || voiceActivity?.status === 'speaking')
  const processing = sending || (mode === 'voice' && voiceActivity?.status === 'processing')
  const status = !connected ? 'Offline' : listening ? 'Listening' : speaking ? 'Speaking' : processing ? 'Working on it' : 'Ready when you are'
  const state = !connected ? 'offline' : listening ? 'listening' : speaking ? 'speaking' : processing ? 'processing' : 'idle'
  useEffect(() => { endRef.current?.scrollIntoView({ block: 'end', behavior: 'instant' }) }, [messages, processing])
  useEffect(() => { if (!connected && isRecording) stopRecording() }, [connected, isRecording, stopRecording])
  const activateVoice = async () => {
    setError('')
    if (isRecording) { stopRecording(); return }
    if (mode === 'voice') unlockAudio?.()
    if (micSource === 'device') {
      if (!isSupported) { setError('This browser does not support voice recognition. Switch to Chat to type your request or choose the PC microphone.'); return }
      startRecording()
    } else {
      try { await api.activateVoice() } catch (err) { setError(err.message || 'Could not activate the PC microphone') }
    }
  }
  const copy = async (text, index) => {
    try { await navigator.clipboard.writeText(text); setCopied(index) }
    catch { setError('Could not copy. Select the text to copy it manually.') }
  }
  const latest = messages[messages.length - 1]
  return (
    <section className={`chat-interface mode-${mode} state-${state}`}>
      <div className="conversation-toolbar"><div className="mode-switch" aria-label="Conversation mode"><button className={mode === 'chat' ? 'active' : ''} onClick={() => setMode?.('chat')} aria-pressed={mode === 'chat'}><MessageSquare size={15} />Chat</button><button className={mode === 'voice' ? 'active' : ''} onClick={() => setMode?.('voice')} aria-pressed={mode === 'voice'}><Waves size={16} />Voice</button></div><span className="live-status" role="status"><i className={`status-dot ${connected ? 'online' : ''}`} />{status}</span></div>
      {mode === 'voice' ? <div className="voice-stage"><p className="eyebrow">A CONVERSATION, WITHOUT THE KEYBOARD</p><h1>Let’s talk.</h1><div className="voice-art"><WaveAnimation isActive={listening} isSpeaking={speaking} isProcessing={processing} /><button className="voice-mic" aria-label={isRecording ? 'Stop listening' : 'Start voice conversation'} disabled={!connected || processing || speaking || (listening && !isRecording)} onClick={activateVoice}>{isRecording ? <MicOff size={29} /> : <Mic size={29} />}</button></div><p className="voice-caption">{interim || (speaking ? speakingText : '') || latest?.content || latest?.text || 'Ideas, questions, or a little help with your day.'}</p><span className="voice-hint">{listening ? 'Listening to you…' : processing ? 'Aiden is working on your request…' : speaking ? 'Aiden is replying…' : 'Tap the microphone to start'}</span></div> : <div className="conversation-scroll">
        {messages.length === 0 ? <div className="welcome"><div className="welcome-art"><WaveAnimation isActive={false} isSpeaking={false} /><span className="welcome-mark">a</span></div><p className="eyebrow">A LITTLE HELP. A LOT OF POSSIBILITIES.</p><h1>What’s on your mind?</h1><p className="welcome-description">Think out loud, ask away, or get something done.<br />Your computer is just a conversation away.</p><div className="suggestions">{suggestions.map(({ icon: Icon, title, detail, prompt }) => <button key={title} onClick={() => { setDraft(prompt); inputRef.current?.focus() }}><Icon size={19} /><strong>{title}</strong><span>{detail}</span><ArrowUpRight className="suggestion-arrow" size={16} /></button>)}</div></div> : <div className="message-list" role="log" aria-label="Conversation">{messages.map((message, index) => {
          const user = message.role === 'user' || message.type === 'user'
          const text = message.content || message.text || ''
          return <article className={`message ${user ? 'user-message' : 'assistant-message'}`} key={message.id || `${message.timestamp}-${index}`}><div className="message-author">{user ? 'You' : <><span className="message-mark">a</span>Aiden</>}</div><div className="message-content">{text}</div>{user && message.delivery === 'failed' && <small className="message-failed">Not sent · Retry from the composer</small>}{!user && <button className="copy-button" aria-label="Copy Aiden response" onClick={() => copy(text, index)}>{copied === index ? <Check size={14} /> : <Copy size={14} />}{copied === index ? 'Copied' : 'Copy'}</button>}</article>
        })}<div ref={endRef} /></div>}
        {processing && <div className="thinking" role="status" aria-label="Aiden is thinking"><span className="thinking-mark" aria-hidden="true">a</span><div className="thinking-detail"><span className="thinking-label">Aiden</span><div className="thinking-activity"><span className="thinking-wave" aria-hidden="true"><i /><i /><i /><i /></span><span>Thinking…</span></div></div></div>}
      </div>}
      <div className="composer-area">
        {mode === 'voice' && audioBlocked && <div className="inline-notice"><Volume2 size={17} /><span>Your browser paused the voice reply.</span><button onClick={resumeAudio}>Play reply</button></div>}
        {mode === 'voice' && audioError && <div className="inline-error" role="alert">{audioError}</div>}
        {error && <div className="inline-error" role="alert">{error}</div>}
        {!connected && <p className="offline-notice">Waiting for your PC. Keep Aiden running to send messages and commands.</p>}
        {interim && mode === 'chat' && <p className="interim-transcript">{interim}</p>}
        {mode === 'chat' && <form className="composer" onSubmit={event => { event.preventDefault(); send(draft) }}><label className="sr-only" htmlFor="message-input">Message Aiden</label><textarea ref={inputRef} id="message-input" rows={2} maxLength={10000} value={draft} onChange={event => setDraft(event.target.value)} placeholder={connected ? 'Ask Aiden anything, or tell it what to do…' : 'Connect your PC to start a conversation…'} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); if (!processing && !speaking && !listening) send(draft) } }} /><div className="composer-bottom"><div className="composer-context"><Monitor size={14} />Runs on your PC</div><div className="composer-actions"><button type="button" className={`icon-button ${isRecording ? 'recording' : ''}`} onClick={activateVoice} disabled={!connected || processing || speaking || (listening && !isRecording)} aria-label={isRecording ? 'Stop listening' : 'Use microphone'}>{isRecording ? <MicOff size={18} /> : <Mic size={18} />}</button><button type="submit" className="send-button" disabled={!connected || !draft.trim() || processing || speaking || listening} aria-label="Send message"><ArrowUp size={19} /></button></div></div></form>}
        <div className="composer-options">{mode === 'voice' ? <><label><Mic size={13} /><select aria-label="Microphone source" value={micSource} onChange={event => setMicSource(event.target.value)} disabled={listening || processing}><option value="device">This device’s microphone</option><option value="pc">PC microphone</option></select></label><button className="audio-toggle" onClick={toggleAudio} aria-pressed={audioEnabled}>{audioEnabled ? <Volume2 size={14} /> : <VolumeX size={14} />}{audioEnabled ? 'Reply audio on this device' : 'Reply audio muted'}</button></> : <span className="text-chat-hint">Text chat · Silent replies<span>Enter to send · Shift + Enter for a new line</span></span>}</div>
      </div>
    </section>
  )
}
export default ChatInterface
