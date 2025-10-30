import React, { useState, useEffect } from 'react'
import { Mic, MicOff } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { toast } from 'react-hot-toast'
import WaveAnimation from './WaveAnimation'
import ShimmerText from './ShimmerText'
import api from '../../lib/api'

const ChatInterface = ({ messages, voiceActivity, connected }) => {
  const [isListening, setIsListening] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [currentText, setCurrentText] = useState('')
  const [userInput, setUserInput] = useState('')
  const [displayText, setDisplayText] = useState('')

  // Update listening and speaking states
  useEffect(() => {
    const listening = voiceActivity?.status === 'listening'
    const speaking = voiceActivity?.speaking || voiceActivity?.status === 'speaking'
    
    // Clear user input when starting to listen (ready for new input)
    if (listening && !isListening) {
      console.log('[ChatInterface] Started listening - clearing user input')
      setUserInput('')
    }
    
    setIsListening(listening)
    setIsSpeaking(speaking)
  }, [voiceActivity, isListening])
  
  // Handle message display
  useEffect(() => {
    console.log('[ChatInterface] Messages updated, total:', messages.length, messages)
    if (messages.length > 0) {
      const latestMessage = messages[messages.length - 1]
      const messageText = latestMessage.content || latestMessage.text || ''
      
      console.log('[ChatInterface] Latest message:', latestMessage)
      
      if (latestMessage.role === 'user') {
        console.log('[ChatInterface] Setting user input:', messageText)
        setUserInput(messageText)
      } else if (latestMessage.role === 'assistant') {
        console.log('[ChatInterface] Setting current text:', messageText)
        setCurrentText(messageText)
      }
    }
  }, [messages])
  
  // Update display text based on state
  useEffect(() => {
    console.log('[ChatInterface] State:', { isListening, isSpeaking, userInput, currentText, voiceActivity: voiceActivity?.status })

    if (isSpeaking && currentText) {
      console.log('[ChatInterface] Displaying assistant text:', currentText)
      setDisplayText(currentText)
    } else if (isListening) {
      // When listening, always clear text for a clean slate.
      console.log('[ChatInterface] Listening: Clearing display.')
      setDisplayText('')
    } else if (voiceActivity?.status === 'processing' && userInput) {
      // After listening, show the user's transcribed input while we process.
      console.log('[ChatInterface] Processing: Displaying user input:', userInput)
      setDisplayText(userInput)
    } else {
      // In any other state (like idle), clear the text.
      // A small delay provides a smoother transition out.
      const timeout = setTimeout(() => {
        console.log('[ChatInterface] Idle or other state: Clearing display text')
        setDisplayText('')
      }, 300)
      return () => clearTimeout(timeout)
    }
  }, [isListening, isSpeaking, userInput, currentText, voiceActivity?.status])

  const handleVoiceActivate = async () => {
    if (!connected) {
      toast.error('Not connected to Aiden')
      return
    }

    try {
      await api.activateVoice()
    } catch (error) {
      toast.error('Failed to activate voice')
      console.error('Voice activation error:', error)
    }
  }

  const getStatusColor = () => {
    if (isListening) return 'bg-emerald-500'
    if (isSpeaking) return 'bg-blue-500'
    if (voiceActivity?.status === 'processing') return 'bg-purple-500'
    return 'bg-emerald-500'
  }

  const getStatusText = () => {
    if (isListening) return 'Listening'
    if (isSpeaking) return 'Speaking'
    if (voiceActivity?.status === 'processing') return 'Thinking'
    return 'Ready'
  }

  return (
    <div className="flex flex-col h-full relative overflow-hidden">
      {/* Enhanced Wave Animation - Full Screen Background */}
      <div className={`wave-container ${isListening || isSpeaking ? 'active' : ''}`}>
        <WaveAnimation isActive={isListening} isSpeaking={isSpeaking} />
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col items-center justify-center relative z-10 p-8">
        <motion.div
          initial={{ scale: 0.8, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 0.5 }}
          className="text-center max-w-4xl w-full"
        >
          {/* Large "Aiden" Text in Center */}
          <motion.h1 
            className="text-8xl font-bold mb-6 bg-gradient-to-r from-blue-400 to-blue-300 bg-clip-text text-transparent"
            animate={{
              scale: isListening ? [1, 1.02, 1] : 1,
            }}
            transition={{ duration: 2, repeat: Infinity }}
          >
            Aiden
          </motion.h1>

          {/* Status Indicator */}
          <div className="flex items-center justify-center gap-3 mb-12">
            <motion.div
              className={`w-3 h-3 rounded-full ${getStatusColor()}`}
              animate={{ scale: [1, 1.3, 1], opacity: [1, 0.7, 1] }}
              transition={{ duration: 2, repeat: Infinity }}
            />
            <span className="text-lg text-white/70 font-medium">{getStatusText()}</span>
          </div>

          {/* Glass Mic Button - Centered with Blue Styling */}
          <motion.div
            className="mb-8 flex justify-center"
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
          >
            <button
              onClick={handleVoiceActivate}
              disabled={!connected}
              className={`liquid-glass-card w-16 h-16 rounded-full flex items-center justify-center transition-all duration-300 ${
                isListening 
                  ? 'bg-emerald-500/20 border-emerald-400/40 shadow-lg shadow-emerald-500/20' 
                  : 'bg-blue-500/10 border-blue-400/30 shadow-lg shadow-blue-500/20'
              } hover:bg-blue-500/20 hover:border-blue-400/50`}
            >
              {isListening ? (
                <MicOff className="w-5 h-5 text-emerald-300 relative z-10" />
              ) : (
                <Mic className="w-5 h-5 text-blue-300 relative z-10" />
              )}
            </button>
          </motion.div>

          {/* Display text directly without box - Gemini Live mode style with Shimmer */}
          <div className="min-h-[120px] flex items-center justify-center">
            <AnimatePresence mode="wait">
              {displayText ? (
                <motion.div
                  key={displayText}
                  initial={{ opacity: 0, y: 15 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -15 }}
                  transition={{ 
                    duration: 0.4,
                    ease: [0.4, 0, 0.2, 1]
                  }}
                  className="max-w-3xl text-center px-8"
                >
                  <ShimmerText 
                    text={displayText}
                    isActive={isSpeaking}
                    className="text-3xl leading-relaxed"
                  />
                </motion.div>
              ) : (
                <motion.p
                  key="ready"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.3 }}
                  className="text-xl text-white/40"
                >
                  Ready to assist
                </motion.p>
              )}
            </AnimatePresence>
          </div>


          {/* Connection Status */}
          <motion.p
            className="mt-6 text-sm text-white/40"
            animate={{ opacity: [0.4, 0.7, 0.4] }}
            transition={{ duration: 3, repeat: Infinity }}
          >
            {!connected ? 'Connecting...' : ''}
          </motion.p>
        </motion.div>
      </div>
    </div>
  )
}

export default ChatInterface