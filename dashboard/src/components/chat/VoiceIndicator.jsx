import React from 'react'
import { motion } from 'framer-motion'
import { Mic, Loader2, Volume2 } from 'lucide-react'

const VoiceIndicator = ({ status, speaking }) => {
  if (status === 'idle' && !speaking) return null

  const getIcon = () => {
    if (speaking) return <Volume2 className="w-5 h-5" />
    if (status === 'listening') return <Mic className="w-5 h-5" />
    if (status === 'processing') return <Loader2 className="w-5 h-5 animate-spin" />
    return null
  }

  const getColor = () => {
    if (speaking) return 'bg-aiden-warning'
    if (status === 'listening') return 'bg-aiden-success'
    if (status === 'processing') return 'bg-aiden-blue'
    return 'bg-muted'
  }

  return (
    <motion.div
      initial={{ scale: 0.8, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      exit={{ scale: 0.8, opacity: 0 }}
      className={`${getColor()} rounded-full p-3 text-white shadow-lg`}
    >
      {status === 'listening' && !speaking && (
        <div className="flex items-center gap-1">
          {[...Array(4)].map((_, i) => (
            <motion.div
              key={i}
              className="w-1 bg-white rounded-full"
              animate={{
                height: [12, 24, 12],
              }}
              transition={{
                duration: 0.8,
                repeat: Infinity,
                delay: i * 0.1,
              }}
            />
          ))}
        </div>
      )}
      
      {(speaking || status === 'processing') && getIcon()}
    </motion.div>
  )
}

export default VoiceIndicator



