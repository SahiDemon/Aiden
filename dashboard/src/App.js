import React, { useState, useEffect } from 'react'
import { Settings } from 'lucide-react'
import { Toaster, toast } from 'react-hot-toast'
import { Button } from './components/ui/button'
import { Badge } from './components/ui/badge'
import ChatInterface from './components/chat/ChatInterface'
import ConversationHistory from './components/chat/ConversationHistory'
import CollapsibleSidebar from './components/layout/CollapsibleSidebar'
import SettingsDialog from './components/settings/SettingsDialog'
import useWebSocket from './hooks/useWebSocket'
import api from './lib/api'

function App() {
  const [showSettings, setShowSettings] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const [conversationMessages, setConversationMessages] = useState([])
  const [isLoading, setIsLoading] = useState(true)

  const {
    connected,
    messages: wsMessages,
    voiceActivity,
    systemMetrics,
    deviceUpdates,
    speakingText,
  } = useWebSocket()

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
      <Toaster position="top-right" toastOptions={{
        className: 'liquid-glass-card',
        style: {
          background: 'rgba(255, 255, 255, 0.08)',
          color: '#fff',
          border: '1px solid rgba(255, 255, 255, 0.15)',
          borderRadius: '12px',
        },
      }} />

      {/* Collapsible Sidebar */}
      <CollapsibleSidebar
        connected={connected}
        systemMetrics={systemMetrics}
        deviceUpdates={deviceUpdates}
        onShowHistory={() => setShowHistory(true)}
        onShowSettings={() => setShowSettings(true)}
      />

      {/* Header - Fixed at top with proper z-index */}
      <header className="fixed top-0 left-0 right-0 liquid-glass-navbar flex items-center justify-between px-6">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-blue-700 flex items-center justify-center shadow-lg">
            <span className="text-white font-bold text-lg">A</span>
          </div>
          <div>
            <h1 className="text-xl font-bold bg-gradient-to-r from-blue-400 to-blue-300 bg-clip-text text-transparent">
              Aiden AI
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

      {/* Main Content - Account for navbar height */}
      <main className="pt-16 h-screen pl-15">
        <div className="h-full">
          {isLoading ? (
            <div className="flex items-center justify-center h-full">
              <div className="liquid-glass-card p-8">
                <p className="text-white/70">Loading...</p>
              </div>
            </div>
          ) : (
            <ChatInterface
              messages={conversationMessages}
              voiceActivity={voiceActivity}
              connected={connected}
              speakingText={speakingText}
            />
          )}
        </div>
      </main>

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
    </div>
  )
}

export default App
