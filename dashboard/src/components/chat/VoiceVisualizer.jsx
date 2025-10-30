import React, { useEffect, useRef } from 'react'
import { motion } from 'framer-motion'

const VoiceVisualizer = ({ isListening }) => {
  const barsCount = 40
  const barsRef = useRef([])

  useEffect(() => {
    if (!isListening) {
      barsRef.current = Array(barsCount).fill(0.1)
      return
    }

    const interval = setInterval(() => {
      barsRef.current = Array(barsCount)
        .fill(0)
        .map(() => Math.random() * 0.8 + 0.2)
    }, 100)

    return () => clearInterval(interval)
  }, [isListening])

  return (
    <div className="flex items-center justify-center gap-1 h-20">
      {Array.from({ length: barsCount }).map((_, i) => (
        <motion.div
          key={i}
          className="bg-gradient-to-t from-blue-500 to-blue-300 rounded-full"
          style={{
            width: '3px',
          }}
          animate={{
            height: isListening
              ? `${20 + Math.random() * 60}%`
              : '10%',
            opacity: isListening ? 0.8 : 0.3,
          }}
          transition={{
            duration: 0.15,
            repeat: isListening ? Infinity : 0,
            repeatType: 'reverse',
            delay: i * 0.02,
          }}
        />
      ))}
    </div>
  )
}

export default VoiceVisualizer

