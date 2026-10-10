import React, { act } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import api from './lib/api'
import useWebSocket from './hooks/useWebSocket'

jest.mock('./lib/api', () => ({ sendMessage: jest.fn(), getActiveTimers: jest.fn() }))
jest.mock('./hooks/useWebSocket', () => jest.fn())
jest.mock('./components/chat/WaveAnimation', () => () => null)
jest.mock('./components/TimerDisplay', () => () => null)
jest.mock('react-hot-toast', () => ({ Toaster: () => null, toast: { success: jest.fn(), error: jest.fn() } }))
jest.mock('./hooks/useWebSpeech', () => ({ useWebSpeech: () => ({ isSupported: false, isRecording: false, stopRecording: jest.fn() }) }))
globalThis.IS_REACT_ACT_ENVIRONMENT = true

test('shows a sent message immediately and reconciles HTTP and WebSocket replies once', async () => {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root = createRoot(container)
  Element.prototype.scrollIntoView = jest.fn()
  let finish
  api.getActiveTimers.mockResolvedValue({ success: true, timers: [] })
  api.sendMessage.mockImplementation(() => new Promise(resolve => { finish = resolve }))
  useWebSocket.mockReturnValue({ connected: true, messages: [] })
  try {
    await act(async () => root.render(<App />))
    const input = container.querySelector('textarea')
    act(() => {
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(input, 'Hello Aiden')
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    act(() => container.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })))
    expect(container.querySelector('[role="log"]').textContent).toContain('Hello Aiden')
    expect(input.value).toBe('')
    expect(container.querySelectorAll('article')).toHaveLength(1)
    const id = api.sendMessage.mock.calls[0][2]
    await act(async () => finish({ success: true, response: 'Hello there' }))
    useWebSocket.mockReturnValue({ connected: true, messages: [
      { role: 'user', content: 'Hello Aiden', client_message_id: id },
      { role: 'assistant', content: 'Hello there', client_message_id: id },
    ] })
    await act(async () => root.render(<App />))
    expect(container.querySelectorAll('article')).toHaveLength(2)
    expect(container.querySelector('[role="log"]').textContent).toContain('Hello there')
  } finally {
    act(() => root.unmount())
    container.remove()
  }
})
