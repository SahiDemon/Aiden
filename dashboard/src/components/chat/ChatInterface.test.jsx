import React, { act } from 'react'
import { createRoot } from 'react-dom/client'
import ChatInterface from './ChatInterface'
import api from '../../lib/api'
globalThis.IS_REACT_ACT_ENVIRONMENT = true
jest.mock('../../lib/api', () => ({ sendMessage: jest.fn(), activateVoice: jest.fn() }))
jest.mock('./WaveAnimation', () => () => <div />)
let mockSpeechCallbacks
jest.mock('../../hooks/useWebSpeech', () => ({ useWebSpeech: callbacks => {
  mockSpeechCallbacks = callbacks
  return { isSupported: false, isRecording: false, startRecording: jest.fn(), stopRecording: jest.fn() }
} }))
let container, root
beforeEach(() => { container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container); jest.clearAllMocks(); Element.prototype.scrollIntoView = jest.fn() })
afterEach(() => { act(() => root.unmount()); container.remove() })
const render = props => act(() => root.render(<ChatInterface connected messages={[]} {...props} />))
const type = text => act(() => {
  const input = container.querySelector('textarea')
  Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(input, text)
  input.dispatchEvent(new Event('input', { bubbles: true }))
})
test('text requests reach the PC and a failed request retains the draft for retry', async () => {
  api.sendMessage.mockRejectedValueOnce(new Error('PC request failed'))
  render(); type('Open calculator')
  await act(async () => container.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })))
  expect(api.sendMessage).toHaveBeenCalledWith('Open calculator', false, expect.any(String))
  expect(container.querySelector('textarea').value).toBe('Open calculator')
  expect(container.querySelector('[role="alert"]').textContent).toContain('PC request failed')
})
test('offline controls prevent submitting commands and display the connection state', () => {
  render({ connected: false })
  type('Open calculator')
  act(() => container.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })))
  expect(api.sendMessage).not.toHaveBeenCalled()
  expect(container.querySelector('[aria-label="Send message"]').disabled).toBe(true)
  expect(container.textContent).toContain('Waiting for your PC')
})
test('unsupported device microphone does not silently activate the PC microphone', () => {
  render(); act(() => container.querySelector('[aria-label="Use microphone"]').click())
  expect(api.activateVoice).not.toHaveBeenCalled()
  expect(container.querySelector('[role="alert"]').textContent).toContain('does not support voice recognition')
})
test('blocked phone reply audio exposes a retry action', () => {
  const resumeAudio = jest.fn()
  render({ mode: 'voice', audioBlocked: true, resumeAudio })
  act(() => [...container.querySelectorAll('button')].find(button => button.textContent === 'Play reply').click())
  expect(resumeAudio).toHaveBeenCalledTimes(1)
})

test('voice mode has microphone and audio controls without a typing composer', () => {
  const unlockAudio = jest.fn()
  render({ mode: 'voice', unlockAudio })
  expect(container.querySelector('textarea')).toBeNull()
  expect(container.querySelector('form')).toBeNull()
  expect(container.querySelector('[aria-label="Microphone source"]')).not.toBeNull()
  act(() => container.querySelector('[aria-label="Start voice conversation"]').click())
  expect(unlockAudio).toHaveBeenCalledTimes(1)
  render({ mode: 'chat' })
  expect(container.querySelector('textarea')).not.toBeNull()
})

test('voice playback failures are visible', () => {
  render({ mode: 'voice', audioError: 'Could not play the voice reply' })
  expect(container.querySelector('[role="alert"]').textContent).toContain('Could not play')
})

test('sending clears the composer immediately and allows drafting the next message', async () => {
  let resolve
  api.sendMessage.mockImplementation(() => new Promise(done => { resolve = done }))
  const onOutgoing = jest.fn(), onCompleted = jest.fn()
  render({ onOutgoing, onCompleted }); type('Hello')
  act(() => container.querySelector('form').dispatchEvent(new Event('submit', { bubbles:true, cancelable:true })))
  expect(container.querySelector('textarea').value).toBe('')
  expect(container.querySelector('textarea').disabled).toBe(false)
  expect(onOutgoing).toHaveBeenCalledWith(expect.any(String), 'Hello')
  type('Next question')
  await act(async () => resolve({ success:true, response:'Hi there' }))
  expect(container.querySelector('textarea').value).toBe('Next question')
  expect(onCompleted).toHaveBeenCalledWith(expect.any(String), 'Hi there')
})

test('voice previews are display-only and the final transcript is sent once', async () => {
  const sendMessage = jest.fn()
  api.sendMessage.mockResolvedValue({ success: true, response: 'Hello' })
  render({ mode: 'voice', sendMessage })
  act(() => mockSpeechCallbacks.onStart())
  act(() => mockSpeechCallbacks.onResult('play', ''))
  expect(sendMessage).toHaveBeenLastCalledWith('voice_transcript', { data: { text: 'play', stage: 'partial' } })
  expect(api.sendMessage).not.toHaveBeenCalled()
  await act(async () => mockSpeechCallbacks.onResult('', 'play Thunder'))
  expect(api.sendMessage).toHaveBeenCalledWith('play Thunder', true, expect.any(String))
  act(() => mockSpeechCallbacks.onEnd())
  expect(sendMessage).toHaveBeenLastCalledWith('voice_transcript', { data: { text: 'play Thunder', stage: 'final' } })
})
test('dictation in text mode stays silent and does not activate the overlay', async () => {
  const sendMessage = jest.fn()
  api.sendMessage.mockResolvedValue({ success: true, response: 'Hello' })
  render({ mode: 'chat', sendMessage })
  act(() => mockSpeechCallbacks.onStart())
  await act(async () => mockSpeechCallbacks.onResult('', 'Hello'))
  expect(sendMessage).not.toHaveBeenCalled()
  expect(api.sendMessage).toHaveBeenCalledWith('Hello', false, expect.any(String))
})
