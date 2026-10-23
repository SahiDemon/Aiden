import React, { act } from 'react'
import { createRoot } from 'react-dom/client'
import ChatInterface from './ChatInterface'
import api from '../../lib/api'

jest.mock('../../lib/api', () => ({ sendMessage: jest.fn(), activateVoice: jest.fn() }))
jest.mock('./WaveAnimation', () => () => <div />)
globalThis.IS_REACT_ACT_ENVIRONMENT = true

let recognition, container, root
const originalRecognition = window.SpeechRecognition
beforeEach(() => {
  window.SpeechRecognition = class {
    constructor() { recognition = this }
    start() { this.onstart() }
    stop() { this.onend() }
    abort() {}
  }
  api.sendMessage.mockResolvedValue({ success: true, response: 'Hello' })
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  Element.prototype.scrollIntoView = jest.fn()
})
afterEach(() => {
  act(() => root.unmount())
  container.remove()
  window.SpeechRecognition = originalRecognition
  jest.clearAllMocks()
})

test.each(['voice', 'chat'])('real recognition sends the correct reply audio mode in %s', async mode => {
  const sendMessage = jest.fn()
  const unlockAudio = jest.fn()
  act(() => root.render(<ChatInterface connected mode={mode} sendMessage={sendMessage} unlockAudio={unlockAudio} />))
  act(() => container.querySelector(mode === 'voice' ? '.voice-mic' : '[aria-label="Use microphone"]').click())
  expect(unlockAudio).toHaveBeenCalledTimes(mode === 'voice' ? 1 : 0)
  if (mode === 'voice') expect(sendMessage).toHaveBeenCalledWith('voice_transcript', { data: { text: '', stage: 'start' } })
  await act(async () => recognition.onresult({ resultIndex: 0, results: [Object.assign([{ transcript: 'How are you' }], { isFinal: true })] }))
  expect(api.sendMessage).toHaveBeenCalledWith('How are you', mode === 'voice', expect.any(String))
  act(() => recognition.onend())
  if (mode === 'chat') expect(sendMessage).not.toHaveBeenCalled()
})
