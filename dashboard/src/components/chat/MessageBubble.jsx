import React from 'react'
import { motion } from 'framer-motion'
import { User, Bot, Sparkles } from 'lucide-react'
import { Avatar, AvatarFallback } from '../ui/avatar'
import { formatRelativeTime } from '../../lib/utils'
import ShimmerText from './ShimmerText'

const MessageBubble = ({ message, isSpeaking = false }) => {
  const isUser = message.type === 'user' || message.role === 'user'
  const isCurrentlySpeaking = isSpeaking && !isUser
  
  return (
    <motion.div
      initial={{ opacity: 0, y: 20, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -10, scale: 0.95 }}
      transition={{ 
        duration: 0.3,
        type: "spring",
        stiffness: 200,
        damping: 20
      }}
      className={`flex gap-3 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}
    >
      <motion.div
        initial={{ scale: 0 }}
        animate={{ scale: 1 }}
        transition={{ delay: 0.1, type: "spring" }}
      >
        <Avatar className={`w-10 h-10 ${
          isUser 
            ? 'bg-gradient-to-br from-blue-500 to-blue-600 shadow-lg shadow-blue-500/50' 
            : 'bg-gradient-to-br from-purple-500 to-indigo-600 shadow-lg shadow-purple-500/50'
        }`}>
          <AvatarFallback>
            {isUser ? (
              <User className="w-5 h-5 text-white" />
            ) : (
              <Bot className="w-5 h-5 text-white" />
            )}
          </AvatarFallback>
        </Avatar>
      </motion.div>

      <div className={`flex flex-col ${isUser ? 'items-end' : 'items-start'} max-w-[75%]`}>
        <motion.div
          className={`rounded-2xl px-5 py-3 relative overflow-hidden ${
            isUser
              ? 'bg-gradient-to-br from-blue-500 to-blue-600 text-white shadow-lg'
              : 'bg-card border border-border/50 shadow-md'
          }`}
          whileHover={{ scale: 1.02 }}
          transition={{ duration: 0.2 }}
        >
          {isCurrentlySpeaking && (
            <motion.div
              className="absolute top-2 right-2"
              animate={{ rotate: 360 }}
              transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
            >
              <Sparkles className="w-4 h-4 text-blue-400" />
            </motion.div>
          )}
          
          <p className="text-sm leading-relaxed whitespace-pre-wrap break-words">
            {isCurrentlySpeaking ? (
              <ShimmerText 
                text={message.text || message.content || ''} 
                isSpeaking={true}
              />
            ) : (
              message.text || message.content || ''
            )}
          </p>
        </motion.div>
        
        <motion.span 
          className="text-xs text-muted-foreground mt-1 px-2"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2 }}
        >
          {message.timestamp ? formatRelativeTime(message.timestamp) : 'Just now'}
        </motion.span>
      </div>
    </motion.div>
  )
}

export default MessageBubble



