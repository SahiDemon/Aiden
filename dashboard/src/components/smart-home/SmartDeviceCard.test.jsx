import React, { act } from 'react'
import { createRoot } from 'react-dom/client'
import SmartDeviceCard from './SmartDeviceCard'
import api from '../../lib/api'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

jest.mock('../../lib/api', () => ({
  __esModule: true,
  default: {
    getESP32Device: jest.fn(),
    controlESP32: jest.fn(),
  },
}))

jest.mock('react-hot-toast', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
  },
}))

const devicePayload = {
  success: true,
  connected: true,
  ip_address: '192.168.1.180',
  device: {
    device_name: 'Fan Remote',
    ip_address: '192.168.1.180',
    summary: {
      state: 'on',
      speed: '2',
      timer: '1',
      mode: 'normal',
      osc: 'off',
    },
    controls: [
      {
        id: 'power',
        label: 'Power',
        feature: 'power',
        kind: 'toggle',
        value: 'on',
        value_label: 'On',
        steps: [
          { key: 'off', label: 'Off' },
          { key: 'on', label: 'On' },
        ],
      },
      {
        id: 'speed',
        label: 'Speed',
        feature: 'speed',
        kind: 'cycle',
        value: '2',
        value_label: 'Speed 2',
        steps: [
          { key: '1', label: 'Speed 1' },
          { key: '2', label: 'Speed 2' },
          { key: '3', label: 'Speed 3' },
        ],
      },
      {
        id: 'timer',
        label: 'Timer',
        feature: 'timer',
        kind: 'cycle',
        value: '1',
        value_label: '1h',
        steps: [
          { key: '0.5', label: '0.5h' },
          { key: '1', label: '1h' },
          { key: '1.5', label: '1.5h' },
          { key: '2', label: '2h' },
          { key: '2.5', label: '2.5h' },
          { key: '3', label: '3h' },
          { key: '3.5', label: '3.5h' },
          { key: '4', label: '4h' },
          { key: '4.5', label: '4.5h' },
          { key: '5', label: '5h' },
          { key: '5.5', label: '5.5h' },
          { key: '6', label: '6h' },
          { key: '6.5', label: '6.5h' },
          { key: '7', label: '7h' },
          { key: '7.5', label: '7.5h' },
          { key: 'off', label: 'Timer Off' },
        ],
      },
      {
        id: 'osc',
        label: 'Oscillation',
        feature: 'osc',
        kind: 'toggle',
        value: 'off',
        value_label: 'Rotation Off',
        steps: [
          { key: 'off', label: 'Rotation Off' },
          { key: 'on', label: 'Rotation On' },
        ],
      },
    ],
  },
}

describe('SmartDeviceCard', () => {
  let container
  let root

  beforeEach(() => {
    jest.clearAllMocks()
    api.getESP32Device.mockResolvedValue(devicePayload)
    api.controlESP32.mockResolvedValue({
      success: true,
      connected: true,
      message: 'Speed updated',
      device: {
        ...devicePayload.device,
        summary: { ...devicePayload.device.summary, speed: '3' },
      },
    })

    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => {
      root.unmount()
    })
    container.remove()
  })

  it('renders runtime controls dynamically and sends exact control updates', async () => {
    await act(async () => {
      root.render(<SmartDeviceCard connected={true} deviceUpdates={null} compact={false} />)
    })

    expect(container.textContent).toContain('Fan Remote')
    expect(container.textContent).toContain('Timer')
    expect(container.textContent).toContain('Oscillation')
    expect(container.textContent).toContain('Power on')
    expect(container.textContent).toContain('Speed 2')

    const speedButton = Array.from(container.querySelectorAll('button')).find((button) =>
      button.textContent.includes('Speed 3')
    )

    await act(async () => {
      speedButton.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })

    expect(api.controlESP32).toHaveBeenCalledWith({ control_id: 'speed', target: '3' })
  })
  it('shows every timer duration in one selector and sends the selected target', async () => {
    await act(async () => root.render(<SmartDeviceCard connected />))
    const timer = container.querySelector('select[aria-label="Turn off after"]')
    expect(timer.options.length).toBe(17)
    await act(async () => { timer.value='7.5'; timer.dispatchEvent(new Event('change',{bubbles:true})) })
    expect(api.controlESP32).toHaveBeenCalledWith({control_id:'timer',target:'7.5'})
  })
  it('keeps physical device controls disabled while the PC is offline', async () => {
    await act(async () => root.render(<SmartDeviceCard connected={false} />))
    const switches = [...container.querySelectorAll('[role="switch"]')]
    expect(switches.length).toBeGreaterThan(0)
    expect(switches.every(button=>button.disabled)).toBe(true)
    expect(api.getESP32Device).not.toHaveBeenCalled()
  })

})
