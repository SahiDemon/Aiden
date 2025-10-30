import { useState, useEffect, useRef, useCallback } from 'react'

export const useWebSocket = (url = 'ws://localhost:5000/api/v1/ws') => {
  const [connected, setConnected] = useState(false)
  const [messages, setMessages] = useState([])
  const [voiceActivity, setVoiceActivity] = useState({ status: 'idle', speaking: false })
  const [systemMetrics, setSystemMetrics] = useState(null)
  const [deviceUpdates, setDeviceUpdates] = useState(null)
  const [speakingText, setSpeakingText] = useState('')
  
  const wsRef = useRef(null)
  const reconnectTimeoutRef = useRef(null)
  const reconnectAttemptsRef = useRef(0)
  const isConnectingRef = useRef(false)
  const shouldReconnectRef = useRef(true)
  const urlRef = useRef(url)
  
  // Update URL ref if it changes
  useEffect(() => {
    urlRef.current = url
  }, [url])

  const connect = useCallback(() => {
    // Don't connect if we shouldn't reconnect (component unmounted)
    if (!shouldReconnectRef.current) {
      console.log('[WebSocket] Component unmounted, skipping connection')
      return
    }
    
    // Prevent multiple simultaneous connection attempts
    if (isConnectingRef.current) {
      console.log('[WebSocket] Already connecting, skipping...')
      return
    }
    
    // Skip if already connected
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      console.log('[WebSocket] Already connected, skipping...')
      return
    }
    
    // Close existing connection if any
    if (wsRef.current) {
      try {
        console.log('[WebSocket] Closing existing connection before creating new one')
        wsRef.current.onclose = null // Prevent reconnect on manual close
        wsRef.current.close()
      } catch (e) {
        console.error('[WebSocket] Error closing existing connection:', e)
      }
      wsRef.current = null
    }
    
    isConnectingRef.current = true
    
    try {
      const ws = new WebSocket(urlRef.current)
      
      ws.onopen = () => {
        console.log('WebSocket connected')
        setConnected(true)
        reconnectAttemptsRef.current = 0
        isConnectingRef.current = false
      }

      ws.onclose = () => {
        console.log('WebSocket disconnected')
        setConnected(false)
        isConnectingRef.current = false
        
        // Only reconnect if component is still mounted
        if (!shouldReconnectRef.current) {
          console.log('[WebSocket] Component unmounted, not reconnecting')
          return
        }
        
        // Exponential backoff reconnection
        const delay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 30000)
        reconnectAttemptsRef.current += 1
        
        reconnectTimeoutRef.current = setTimeout(() => {
          console.log(`Reconnecting... (attempt ${reconnectAttemptsRef.current})`)
          connect()
        }, delay)
      }

      ws.onerror = (error) => {
        console.error('WebSocket error:', error)
        isConnectingRef.current = false
      }

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          console.log('[WebSocket] Received:', data)
          
          switch (data.type) {
            case 'connected':
              console.log('Connected to Aiden API')
              break
            
            case 'message':
              console.log('[WebSocket] New message:', data.data)
              setMessages(prev => {
                const newMessages = [...prev, data.data]
                console.log('[WebSocket] Messages updated:', newMessages)
                return newMessages
              })
              break
            
            case 'voice_activity':
              console.log('[WebSocket] Voice activity:', data.data)
              setVoiceActivity(data.data)
              break
            
            case 'system_metric':
              setSystemMetrics(data.data)
              break
            
            case 'device_update':
            case 'esp32_update':
              setDeviceUpdates(data)
              break
            
            case 'voice_activate':
              // Voice activation triggered from dashboard
              console.log('Voice activation triggered')
              setVoiceActivity(prev => ({ ...prev, status: 'listening' }))
              break
            
            case 'assistant_speaking':
              // Aiden is speaking - get the text for display
              setSpeakingText(data.data?.text || '')
              break
              
            case 'pong':
              // Heartbeat response
              break
            
            case 'ping':
              // Server is checking if we are alive
              sendMessage('pong')
              break
              
            default:
              console.log('[WebSocket] Unknown message type:', data.type, data)
          }
        } catch (error) {
          console.error('Error parsing WebSocket message:', error)
        }
      }

      wsRef.current = ws
    } catch (error) {
      console.error('Error creating WebSocket:', error)
      isConnectingRef.current = false
    }
  }, []) // No dependencies - stable callback

  useEffect(() => {
    console.log('[WebSocket] Initializing connection...')
    shouldReconnectRef.current = true
    connect()

    // Heartbeat
    const heartbeat = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'ping' }))
      }
    }, 30000)

    return () => {
      console.log('[WebSocket] Cleanup: closing connection and preventing reconnects')
      shouldReconnectRef.current = false
      clearInterval(heartbeat)
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
        reconnectTimeoutRef.current = null
      }
      isConnectingRef.current = false
      if (wsRef.current) {
        // Remove event listeners to prevent reconnection on cleanup
        wsRef.current.onclose = null
        wsRef.current.onerror = null
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [connect])

  const sendMessage = useCallback((type, data) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type, ...data }))
    } else {
      console.warn('WebSocket is not connected')
    }
  }, [])

  return {
    connected,
    messages,
    voiceActivity,
    systemMetrics,
    deviceUpdates,
    speakingText,
    sendMessage,
  }
}

export default useWebSocket



