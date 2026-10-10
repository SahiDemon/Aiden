import { useState, useEffect, useRef, useCallback } from 'react'

const getWsUrl = () => {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.hostname;
  const portStr = window.location.port ? `:${window.location.port}` : '';
  return `${protocol}//${host}${portStr}/api/v1/ws`;
};

export const useWebSocket = (url = getWsUrl()) => {
  const [connected, setConnected] = useState(false)
  const [messages, setMessages] = useState([])
  const [voiceActivity, setVoiceActivity] = useState({ status: 'idle', speaking: false })
  const [systemMetrics, setSystemMetrics] = useState(null)
  const [deviceUpdates, setDeviceUpdates] = useState(null)
  const [speakingText, setSpeakingText] = useState('')
  const [timerUpdates, setTimerUpdates] = useState(null)
  const [audioBlocked, setAudioBlocked] = useState(false)
  const [audioEnabled, setAudioEnabled] = useState(true)
  const audioEnabledRef = useRef(true)
  const audioRef = useRef(null)
  const audioQueueRef = useRef([])

  const playNextAudio = useCallback(() => {
    if (audioRef.current || !audioEnabledRef.current) return
    const item = audioQueueRef.current.shift()
    if (!item) return
    const audio = new Audio(item.audio_uri)
    const report = state => {
      if (item.source === 'web' && item.speech_id && wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'tts_playback', data: {
          speech_id: item.speech_id, state, position: audio.currentTime || 0,
        } }))
      }
    }
    let clock = null
    const stopClock = () => { if (clock !== null) { clearInterval(clock); clock = null } }
    audio.reportEnd = () => { stopClock(); report('ended') }
    audio.onpause = () => {
      stopClock()
      if (audioRef.current === audio) {
        report('blocked')
        setVoiceActivity(prev => ({ ...prev, status: 'idle', speaking: false }))
      }
    }
    audio.ontimeupdate = () => report('progress')
    audioRef.current = audio
    audio.onplaying = () => {
      report('playing')
      stopClock()
      if (item.source === 'web' && item.speech_id) clock = setInterval(() => report('progress'), 50)
      setAudioBlocked(false)
      setVoiceActivity(prev => ({ ...prev, status: 'speaking', speaking: true }))
    }
    const finish = () => {
      if (audioRef.current !== audio) return
      stopClock()
      report('ended')
      audioRef.current = null
      setAudioBlocked(false)
      setVoiceActivity(prev => ({ ...prev, status: 'idle', speaking: false }))
      playNextAudio()
    }
    audio.onended = finish
    audio.onerror = finish
    audio.play().catch(() => {
      if (audioRef.current !== audio) return
      report('blocked')
      setAudioBlocked(true)
      setVoiceActivity(prev => ({ ...prev, status: 'idle', speaking: false }))
    })
  }, [])
  const resumeAudio = useCallback(() => {
    audioRef.current?.play().then(() => setAudioBlocked(false)).catch(() => setAudioBlocked(true))
  }, [])
  const toggleAudio = useCallback(() => {
    const enabled = !audioEnabledRef.current
    audioEnabledRef.current = enabled
    setAudioEnabled(enabled)
    if (!enabled) {
      audioRef.current?.reportEnd?.()
      audioRef.current?.pause()
      audioRef.current = null
      audioQueueRef.current = []
      setAudioBlocked(false)
      setVoiceActivity(prev => ({ ...prev, status: 'idle', speaking: false }))
    }
  }, [])
  
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
      return
    }
    
    // Prevent multiple simultaneous connection attempts
    if (isConnectingRef.current) {
      return
    }
    
    // Skip if already connected
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return
    }
    
    // Close existing connection if any
    if (wsRef.current) {
      try {
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
        setConnected(true)
        reconnectAttemptsRef.current = 0
        isConnectingRef.current = false
      }

      ws.onclose = () => {
        setConnected(false)
        isConnectingRef.current = false
        
        // Only reconnect if component is still mounted
        if (!shouldReconnectRef.current) {
          return
        }
        
        // Exponential backoff reconnection
        const delay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 30000)
        reconnectAttemptsRef.current += 1
        
        reconnectTimeoutRef.current = setTimeout(() => {
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

          switch (data.type) {
            case 'connected':
              break
            
            case 'message':
              setMessages(prev => {
                const newMessages = [...prev, data.data]
                return newMessages
              })
              break
            
            case 'voice_activity':
              setVoiceActivity(audioRef.current && !audioRef.current.paused
                ? { ...data.data, status: 'speaking', speaking: true }
                : data.data)
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
              setVoiceActivity(prev => ({ ...prev, status: 'listening' }))
              break
            
            case 'assistant_speaking':
              // Aiden is speaking - get the text for display
              setSpeakingText(data.data?.text || '')
              break
            
            case 'timer_update':
              // Timer state changed (created, cancelled, completed)
              setTimerUpdates(data.data)
              break
              
            case 'tts_audio':
              if (data.data?.audio_uri && audioEnabledRef.current) {
                audioQueueRef.current.push(data.data)
                playNextAudio()
              }
              break

              
            case 'pong':
              // Heartbeat response
              break
            
            case 'ping':
              // Server is checking if we are alive
              ws.send(JSON.stringify({ type: 'pong' }))
              break
              
            default:
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
  }, [playNextAudio])

  useEffect(() => {
    shouldReconnectRef.current = true
    connect()

    // Heartbeat
    const heartbeat = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'ping' }))
      }
    }, 30000)

    return () => {
      shouldReconnectRef.current = false
      audioRef.current?.reportEnd?.()
      audioRef.current?.pause()
      audioRef.current = null
      audioQueueRef.current = []
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
    timerUpdates,
    sendMessage,
    audioBlocked,
    resumeAudio,
    audioEnabled,
    toggleAudio,
  }
}

export default useWebSocket
