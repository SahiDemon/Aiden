const API_BASE = '/api/v1'

class ApiClient {
  constructor() {
    this.baseUrl = API_BASE
  }

  async request(endpoint, options = {}) {
    const url = `${this.baseUrl}${endpoint}`
    const config = {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      ...options,
    }

    try {
      const response = await fetch(url, config)
      const data = await response.json()

      if (!response.ok) {
        throw new Error(data.detail || data.message || 'Request failed')
      }

      return data
    } catch (error) {
      console.error(`API Error [${endpoint}]:`, error)
      throw error
    }
  }

  // Settings
  async getSettings() {
    return this.request('/settings')
  }

  async updateSettings(data) {
    return this.request('/settings', {
      method: 'PUT',
      body: JSON.stringify({ settings: data }),
    })
  }

  async getProviderModels(provider) {
    return this.request(`/settings/providers/models?provider=${encodeURIComponent(provider)}`)
  }

  // Messaging
  async sendMessage(message, isVoice = false, clientMessageId) {
    return this.request('/conversation/message', {
      method: 'POST',
      body: JSON.stringify({ message, input_type: isVoice ? 'voice' : 'text', source: 'web', client_message_id: clientMessageId }),
    })
  }

  // Conversations
  async newConversation() {
    return this.request('/conversation/new', { method: 'POST' })
  }

  async resumeConversation(id) {
    return this.request(`/conversations/${encodeURIComponent(id)}/resume`, { method: 'POST' })
  }

  async getConversations() {
    return this.request('/conversations')
  }

  async getConversation(id) {
    return this.request(`/conversations/${id}`)
  }

  async deleteConversation(id) {
    return this.request(`/conversations/${id}`, {
      method: 'DELETE',
    })
  }

  async getConversationHistory(limit = 50) {
    return this.request(`/conversation/history?limit=${limit}`)
  }

  // ESP32 Devices
  async getDevices() {
    return this.request('/esp32/devices')
  }

  async getESP32Device() {
    return this.request('/esp32/device')
  }

  async controlDevice(deviceId, command) {
    return this.request('/esp32/control', {
      method: 'POST',
      body: JSON.stringify({ device_id: deviceId, command }),
    })
  }

  async controlESP32(payload) {
    return this.request('/esp32/control', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  }

  // System Stats
  async getSystemStatus() {
    return this.request('/system/status')
  }

  async getHealth() {
    return this.request('/health')
  }

  // Active Timers
  async getActiveTimers() {
    return this.request('/timers')
  }

  async cancelTimer(id) {
    return this.request(`/timers/${id}`, {
      method: 'DELETE',
    })
  }

  // Voice Interaction
  async activateVoice() {
    return this.request('/voice/activate', {
      method: 'POST',
    })
  }
}

const api = new ApiClient()
export default api
