import React, { act } from 'react'
import { createRoot } from 'react-dom/client'
import useWebSocket from './useWebSocket'
globalThis.IS_REACT_ACT_ENVIRONMENT = true
let state, socket, container, root, audios
const OriginalAudio = global.Audio
const OriginalSocket = global.WebSocket
function Probe() { state = useWebSocket('ws://test'); return null }
beforeEach(() => {
  audios = []
  global.WebSocket = class { static OPEN = 1; constructor() { socket = this; this.readyState = 1 } send = jest.fn(); close() {} }
  global.Audio = class { constructor(uri) { this.src = uri; this.paused = true; this.play = jest.fn(() => Promise.reject(new DOMException('Autoplay blocked', 'NotAllowedError'))); this.pause = jest.fn(); audios.push(this) } }
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container)
  act(() => root.render(<Probe />))
})
afterEach(() => { act(() => root.unmount()); container.remove(); global.Audio = OriginalAudio; global.WebSocket = OriginalSocket })
const receive = async uri => act(async () => { socket.onmessage({ data: JSON.stringify({ type: 'tts_audio', data: { audio_uri: uri } }) }) })
test('blocked phone audio can be retried and replies play in sequence', async () => {
  await receive('reply-1'); expect(state.audioBlocked).toBe(true)
  await receive('reply-2'); expect(audios).toHaveLength(1)
  audios[0].play.mockImplementation(() => { audios[0].paused = false; audios[0].onplaying(); return Promise.resolve() })
  await act(async () => state.resumeAudio())
  expect(state.audioBlocked).toBe(false); expect(state.voiceActivity.status).toBe('speaking')
  act(() => audios[0].onended())
  await act(async () => {})
  expect(audios).toHaveLength(1); expect(audios[0].src).toBe('reply-2')
})
test('muting clears queued audio and prevents new playback on this device', async () => {
  await receive('reply-1'); await receive('reply-2')
  act(() => state.toggleAudio())
  expect(audios[0].pause).toHaveBeenCalled(); expect(state.audioEnabled).toBe(false); expect(state.audioBlocked).toBe(false)
  await receive('reply-3'); expect(audios).toHaveLength(1)
})

test('microphone gesture enables the same browser player used for subsequent replies', async () => {
  const MockAudio = global.Audio
  global.Audio = class extends MockAudio {
    constructor(uri) {
      super(uri)
      this.play.mockImplementation(() => { this.paused = false; this.onplaying?.(); return Promise.resolve() })
    }
  }
  act(() => state.unlockAudio())
  const player = audios[0]
  await act(async () => {})
  await receive('reply-1')
  expect(audios).toHaveLength(1)
  expect(player.src).toBe('reply-1')
  expect(state.voiceActivity.status).toBe('speaking')
  act(() => player.onended())
  await receive('reply-2')
  expect(audios).toHaveLength(1)
  expect(player.src).toBe('reply-2')
})

test('unsupported reply audio shows an error instead of silently finishing', async () => {
  await receive('broken-reply')
  act(() => audios[0].onerror())
  expect(state.audioError).toContain('Could not play the voice reply')
  expect(state.audioBlocked).toBe(false)
  expect(state.voiceActivity.status).toBe('idle')
})

test('browser playback reports its real audio clock and stops reporting when muted', async () => {
  jest.useFakeTimers()
  try {
    await act(async () => socket.onmessage({ data: JSON.stringify({ type: 'tts_audio', data: {
      audio_uri: 'voice-reply', source: 'web', speech_id: 'turn1',
    } }) }))
    audios[0].play.mockImplementation(() => { audios[0].paused = false; audios[0].onplaying(); return Promise.resolve() })
    await act(async () => state.resumeAudio())
    audios[0].currentTime = .65
    act(() => jest.advanceTimersByTime(50))
    const events = socket.send.mock.calls.map(([message]) => JSON.parse(message))
    expect(events).toContainEqual({ type: 'tts_playback', data: { speech_id: 'turn1', state: 'progress', position: .65 } })
    act(() => state.toggleAudio())
    expect(JSON.parse(socket.send.mock.calls.at(-1)[0]).data.state).toBe('ended')
    const count = socket.send.mock.calls.length
    act(() => jest.advanceTimersByTime(250))
    expect(socket.send.mock.calls.length).toBe(count)
  } finally { jest.useRealTimers() }
})
