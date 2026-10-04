import React, { useState, useEffect } from 'react'
import { Settings } from 'lucide-react'
import { Toaster, toast } from 'react-hot-toast'
import { Button } from './components/ui/button'
import { Badge } from './components/ui/badge'
import ChatInterface from './components/chat/ChatInterface'
import ConversationHistory from './components/chat/ConversationHistory'
import CollapsibleSidebar from './components/layout/CollapsibleSidebar'
import SettingsDialog from './components/settings/SettingsDialog'
import TimerDisplay from './components/TimerDisplay'
import SystemStats from './components/system/SystemStats'
import SmartDeviceCard from './components/smart-home/SmartDeviceCard'
import BottomNav from './components/layout/BottomNav'
import useWebSocket from './hooks/useWebSocket'
import api from './lib/api'

function App() {
  const [activeTab, setActiveTab] = useState('chat')
  const [showSettings, setShowSettings] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const [conversationMessages, setConversationMessages] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [activeTimers, setActiveTimers] = useState([])

  const {
    connected,
    messages: wsMessages,
    voiceActivity,
    systemMetrics,
    deviceUpdates,
    speakingText,
    timerUpdates,
  } = useWebSocket()

  // Load active timers on component mount
  useEffect(() => {
    const loadTimers = async () => {
      try {
        const response = await api.getActiveTimers()
        if (response.success) {
          setActiveTimers(response.timers || [])
        }
      } catch (error) {
        console.error('Error loading timers:', error)
      }
    }

    if (connected) {
      loadTimers()
    }
  }, [connected])

  // Handle timer updates from WebSocket
  useEffect(() => {
    if (!timerUpdates) return

    console.log('[App] Timer update received:', timerUpdates)
    
    // Real-time timer updates via WebSocket
    const loadTimers = async () => {
      try {
        const response = await api.getActiveTimers()
        console.log('[App] Loaded timers after WebSocket update:', response)
        if (response.success) {
          setActiveTimers(response.timers || [])
          console.log('[App] Active timers set to:', response.timers || [])
        }
      } catch (error) {
        console.error('Error loading timers after WebSocket update:', error)
      }
    }

    loadTimers()
  }, [timerUpdates])

  // Handle timer update callback
  const handleTimerUpdate = async () => {
    try {
      const response = await api.getActiveTimers()
      if (response.success) {
        setActiveTimers(response.timers || [])
      }
    } catch (error) {
      console.error('Error updating timers:', error)
    }
  }

  // Fetch initial conversation history
  useEffect(() => {
    const loadHistory = async () => {
      try {
        setIsLoading(true)
        // Don't load old messages - only show current session messages from WebSocket
        setConversationMessages([])
      } catch (error) {
        console.error('Error loading conversation history:', error)
      } finally {
        setIsLoading(false)
      }
    }

    loadHistory()
  }, [])

  // Handle new conversation
  const handleNewConversation = async () => {
    try {
      // Clear current messages
      setConversationMessages([])
      
      // Start new conversation via voice activation
      await api.activateVoice()
      toast.success('New conversation started')
    } catch (error) {
      toast.error('Failed to start new conversation')
      console.error('New conversation error:', error)
    }
  }

  // Handle conversation selection from history
  const handleSelectConversation = async (conversation) => {
    try {
      setIsLoading(true)
      const response = await api.getConversation(conversation.id)
      if (response.success) {
        setConversationMessages(response.messages || [])
        toast.success('Conversation loaded')
      }
    } catch (error) {
      toast.error('Failed to load conversation')
      console.error('Load conversation error:', error)
    } finally {
      setIsLoading(false)
    }
  }

  // Merge WebSocket messages with conversation messages
  useEffect(() => {
    if (wsMessages.length > 0) {
      setConversationMessages(prev => {
        const newMessages = [...prev]
        wsMessages.forEach(wsMsg => {
          // Check if message already exists by comparing role, content, and timestamp
          const exists = newMessages.find(m => 
            m.role === wsMsg.role && 
            m.content === wsMsg.content &&
            m.timestamp === wsMsg.timestamp
          )
          if (!exists) {
            console.log('[App] Adding new message:', wsMsg)
            newMessages.push(wsMsg)
          }
        })
        console.log('[App] Total messages:', newMessages.length)
        return newMessages
      })
    }
  }, [wsMessages])

  // Show connection status
  useEffect(() => {
    if (connected) {
      toast.success('Connected to Aiden', {
        id: 'connection',
        duration: 2000,
      })
    } else {
      toast.error('Disconnected from Aiden', {
        id: 'connection',
        duration: Infinity,
      })
    }
  }, [connected])

  return (
    <div className="min-h-screen gradient-bg relative overflow-hidden">
      <Toaster 
        position="top-right" 
        containerClassName="!top-4 md:!top-20 !right-4"
        toastOptions={{
          className: 'liquid-glass-card',
          style: {
            background: 'rgba(255, 255, 255, 0.08)',
            color: '#fff',
            border: '1px solid rgba(255, 255, 255, 0.15)',
            borderRadius: '12px',
            marginTop: '0.5rem', // Additional spacing between toasts
          },
        }} 
      />

      {/* Collapsible Sidebar - Hidden on Mobile */}
      <div className="hidden md:block">
        <CollapsibleSidebar
          connected={connected}
          systemMetrics={systemMetrics}
          deviceUpdates={deviceUpdates}
          onShowHistory={() => setShowHistory(true)}
          onShowSettings={() => setShowSettings(true)}
        />
      </div>

      {/* Header - Hidden on Mobile, Fixed at top on Desktop */}
      <header className="hidden md:flex fixed top-0 left-0 right-0 liquid-glass-navbar items-center justify-between px-6">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-blue-700 flex items-center justify-center shadow-lg border border-blue-400/30">
            <span className="text-white font-bold text-lg" style={{ fontFamily: "'Space Grotesk', 'Inter', sans-serif" }}>A</span>
          </div>
          <div>
            <h1 
              className="text-xl font-black tracking-widest bg-gradient-to-r from-white via-blue-100 to-blue-300 bg-clip-text text-transparent"
              style={{ fontFamily: "'Space Grotesk', 'Inter', sans-serif" }}
            >
              AIDEN
            </h1>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <Button
            onClick={handleNewConversation}
            className="bg-blue-500/10 hover:bg-blue-500/20 border border-blue-400/30 text-blue-200 px-4 py-2 shadow-lg shadow-blue-500/10"
          >
            New Conversation
          </Button>
          
          <Badge 
            variant={connected ? "default" : "destructive"}
            className={`${connected ? 'bg-emerald-500/20 border-emerald-400/30 text-emerald-200' : 'bg-red-500/20 border-red-400/30 text-red-200'}`}
          >
            {connected ? 'Online' : 'Offline'}
          </Badge>
          
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setShowSettings(true)}
            className="w-8 h-8 text-blue-200/70 hover:text-blue-200 hover:bg-blue-500/10"
          >
            <Settings className="w-4 h-4" />
          </Button>
        </div>
      </header>

      {/* Main Content - Account for navbar height on desktop, bottom nav height on mobile */}
      <main className="md:pt-16 md:pl-15 h-[100dvh] pb-20 md:pb-0 overflow-hidden">
        <div className="h-full">
          {isLoading ? (
            <div className="flex items-center justify-center h-full">
              <div className="liquid-glass-card p-8">
                <p className="text-white/70">Loading...</p>
              </div>
            </div>
          ) : (
            <>
              <div className={`h-full ${activeTab === 'chat' ? 'block' : 'hidden md:block'}`}>
                <ChatInterface
                  messages={conversationMessages}
                  voiceActivity={voiceActivity}
                  connected={connected}
                  speakingText={speakingText}
                />
              </div>
              <div className={`h-full ${activeTab === 'activity' ? 'block' : 'hidden'} md:hidden overflow-y-auto p-4 space-y-4 pb-28`}>
                <SmartDeviceCard
                  connected={connected}
                  deviceUpdates={deviceUpdates}
                  compact={false}
                />
                <SystemStats
                  connected={connected}
                  systemMetrics={systemMetrics}
                  compact={false}
                />
              </div>
            </>
          )}
        </div>
      </main>

      {/* Mobile Bottom Navigation */}
      <BottomNav 
        activeTab={activeTab} 
        setActiveTab={setActiveTab} 
        onShowSettings={() => setShowSettings(true)}
      />

      {/* Settings Dialog */}
      <SettingsDialog
        open={showSettings}
        onOpenChange={setShowSettings}
      />

      {/* Conversation History Dialog */}
      <ConversationHistory
        isOpen={showHistory}
        onClose={() => setShowHistory(false)}
        onSelectConversation={handleSelectConversation}
      />

      {/* Timer Display */}
      <TimerDisplay
        timers={activeTimers}
        onTimerUpdate={handleTimerUpdate}
      />
    </div>
  )
}

export default App
