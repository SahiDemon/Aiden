import React, { useState, useEffect } from 'react'
import { Mic, MicOff } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { toast } from 'react-hot-toast'
import WaveAnimation from './WaveAnimation'
import ShimmerText from './ShimmerText'
import api from '../../lib/api'
import { useWebSpeech } from '../../hooks/useWebSpeech'

const ChatInterface = ({ messages, voiceActivity, connected }) => {
  const [isListening, setIsListening] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [currentText, setCurrentText] = useState('')
  const [userInput, setUserInput] = useState('')
  const [displayText, setDisplayText] = useState('')
  const [isClientListening, setIsClientListening] = useState(false)

  // Integrate Web Speech API
  const { isSupported, isRecording, startRecording, stopRecording } = useWebSpeech({
    onResult: (interim, final) => {
      // Show interim while speaking
      if (interim) setDisplayText(interim);
      if (final) {
        setDisplayText(final);
        setUserInput(final); // Ensure userInput has the NEW command for the processing phase
        // Send final transcription to Aiden!
        api.sendMessage(final, true).catch(err => {
          console.error("Failed to send message:", err);
          toast.error("Failed to send message");
        });
        setIsClientListening(false);
      }
    },
    onEnd: () => setIsClientListening(false),
    onError: (err) => {
      console.error('Speech error:', err);
      if (err === 'not-allowed') {
        toast.error('Microphone access denied. Try using HTTPS.');
      }
      setIsClientListening(false);
    }
  });

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
    let timeoutId;

    if (isSpeaking && currentText) {
      console.log('[ChatInterface] Displaying assistant text:', currentText)
      setDisplayText(currentText)
    } else if (isListening || isClientListening) {
      // When listening, always clear text for a clean slate, UNLESS we have interim transcript
      if (!isClientListening) {
        console.log('[ChatInterface] Listening: Clearing display.')
        setDisplayText('')
      }
    } else if (voiceActivity?.status === 'processing' && userInput) {
      // After listening, show the user's transcribed input while we process.
      console.log('[ChatInterface] Processing: Displaying user input:', userInput)
      setDisplayText(userInput)
    } else if (voiceActivity?.status === 'idle') {
      // Clear the text after 2.5 seconds of being idle
      timeoutId = setTimeout(() => {
        setDisplayText('')
      }, 2500)
    }
    
    return () => {
      if (timeoutId) clearTimeout(timeoutId)
    }
  }, [isListening, isSpeaking, userInput, currentText, voiceActivity?.status, isClientListening])

  const handleVoiceActivate = async () => {
    if (!connected) {
      toast.error('Not connected to Aiden')
      return
    }

    if (isSupported) {
      // Use client-side Web Speech API if supported (Phone/Chrome MVP)
      if (isRecording || isClientListening) {
        stopRecording()
        setIsClientListening(false)
      } else {
        startRecording()
        setIsClientListening(true)
      }
    } else {
      // Fallback to PC Microphone
      try {
        await api.activateVoice()
      } catch (error) {
        toast.error('Failed to activate PC voice')
        console.error('Voice activation error:', error)
      }
    }
  }

  const getStatusColor = () => {
    if (!connected) return 'bg-red-500'
    if (isListening || isClientListening) return 'bg-emerald-500'
    if (isSpeaking) return 'bg-blue-500'
    if (voiceActivity?.status === 'processing') return 'bg-purple-500'
    return 'bg-emerald-500'
  }

  const getStatusText = () => {
    if (!connected) return 'Disconnected'
    if (isListening || isClientListening) return 'Listening'
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
          {/* Large "AIDEN" Text in Center */}
          <motion.h1 
            className="text-6xl md:text-8xl font-black tracking-[0.2em] mb-4 bg-gradient-to-r from-white via-blue-100 to-blue-300 bg-clip-text text-transparent uppercase drop-shadow-sm"
            style={{ fontFamily: "'Space Grotesk', 'Inter', sans-serif" }}
            animate={{
              scale: isListening ? [1, 1.02, 1] : 1,
            }}
            transition={{ duration: 2, repeat: Infinity }}
          >
            AIDEN
          </motion.h1>

          {/* Status Indicator */}
          <div className="flex items-center justify-center gap-3 mb-12">
            <motion.div
              className={`w-3 h-3 rounded-full ${getStatusColor()}`}
              animate={{ scale: [1, 1.3, 1], opacity: [1, 0.7, 1] }}
              transition={{ duration: 2, repeat: Infinity }}
            />
            <span className="text-base md:text-lg text-white/70 font-medium">{getStatusText()}</span>
          </div>

          {/* Glass Mic Button - Centered with Blue Styling */}
          <motion.div
            className="mb-8 mt-12 flex justify-center"
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
          >
            <button
              onClick={handleVoiceActivate}
              disabled={!connected}
              className={`mic-glow-button w-32 h-32 md:w-32 md:h-32 rounded-full flex items-center justify-center transition-all duration-300 ${
                (isListening || isClientListening)
                  ? 'border-emerald-400/60 shadow-lg shadow-emerald-500/40' 
                  : ''
              }`}
            >
              {(isListening || isClientListening) ? (
                <MicOff className="w-12 h-12 text-emerald-300 relative z-10 stroke-1" />
              ) : (
                <Mic className="w-12 h-12 text-blue-200 relative z-10 stroke-1" />
              )}
            </button>
          </motion.div>

          {/* Display text directly without box - Gemini Live mode style with Shimmer */}
          <div className="min-h-[80px] flex items-center justify-center">
            <AnimatePresence mode="wait">
              {displayText ? (
                <motion.div
                  key="display-text"
                  initial={{ opacity: 0, y: 15 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -15 }}
                  transition={{ 
                    duration: 0.4,
                    ease: [0.4, 0, 0.2, 1]
                  }}
                  className="max-w-3xl text-center px-4 md:px-8"
                >
                  <ShimmerText 
                    text={displayText}
                    isActive={voiceActivity?.status === 'processing' || isSpeaking}
                    className="text-xl md:text-3xl leading-relaxed text-slate-300 font-light"
                  />
                </motion.div>
              ) : (
                <motion.p
                  key="ready"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.3 }}
                  className="text-lg md:text-xl text-slate-400 font-light"
                >
                  {connected ? 'Ready to assist' : 'Disconnected from Aiden'}
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
