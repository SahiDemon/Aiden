import React, { useState, useEffect, useRef } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  TextField,
  IconButton,
  Paper,
  Avatar,
  Chip,
  Divider
} from '@mui/material';
import { Send, Mic, Person, SmartToy } from '@mui/icons-material';
import { motion, AnimatePresence } from 'framer-motion';
import { formatDistanceToNow } from 'date-fns';
import ActionCard from './ActionCard';

// CSS-in-JS animations
const pulseKeyframes = {
  '0%, 100%': { opacity: 1, transform: 'scale(1)' },
  '50%': { opacity: 0.7, transform: 'scale(1.05)' }
};

const spinKeyframes = {
  from: { transform: 'rotate(0deg)' },
  to: { transform: 'rotate(360deg)' }
};

const MessageBubble = ({ message, isUser, socket }) => {
  const getMessageIcon = () => {
    if (isUser) {
      return message.input_type === 'voice' ? <Mic sx={{ fontSize: 16 }} /> : <Person sx={{ fontSize: 16 }} />;
    }
    return <SmartToy sx={{ fontSize: 16 }} />;
  };

  const getMessageTypeColor = () => {
    if (isUser) {
      return message.input_type === 'voice' ? '#4c82f7' : '#6a96ff';
    }
    
    switch (message.message_type) {
      case 'system': return '#666';
      case 'error': return '#f87171';
      case 'follow_up': return '#f7c94c';
      case 'goodbye': return '#4ade80';
      case 'action_card': return '#4c82f7';
      default: return '#4c82f7';
    }
  };

  const handleActionClick = (item, actionType) => {
    // Send action item click to backend
    if (socket) {
      socket.emit('action_item_clicked', {
        item: item,
        action_type: actionType
      });
    }
  };

  // Handle action cards
  if (!isUser && message.message_type === 'action_card' && typeof message.text === 'object') {
    // Validate action object structure
    const action = message.text;
    if (!action || typeof action !== 'object' || !action.type) {
      // Fallback to regular message if action is malformed
      console.warn('Malformed action card data:', action);
      return (
        <motion.div
          initial={{ opacity: 0, y: 20, scale: 0.95 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.3 }}
          className="message-bubble"
        >
          <Box sx={{ 
            display: 'flex', 
            justifyContent: 'flex-start',
            mb: 2
          }}>
            <Paper
              elevation={0}
              sx={{
                maxWidth: '70%',
                p: 2,
                borderRadius: 3,
                background: '#1a1a1a',
                border: '1px solid #2a2a2a',
                color: 'white'
              }}
            >
              <Typography variant="body1">
                Action card data error - showing as text: {JSON.stringify(action)}
              </Typography>
            </Paper>
          </Box>
        </motion.div>
      );
    }

    return (
      <motion.div
        initial={{ opacity: 0, y: 20, scale: 0.95 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.3 }}
        className="message-bubble"
      >
        <Box sx={{ 
          display: 'flex', 
          justifyContent: 'flex-start',
          mb: 2
        }}>
          <Box sx={{ maxWidth: '85%', width: '100%' }}>
            <ActionCard 
              action={action} 
              onItemClick={handleActionClick}
            />
          </Box>
        </Box>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.3 }}
      className="message-bubble"
    >
      <Box sx={{ 
        display: 'flex', 
        justifyContent: isUser ? 'flex-end' : 'flex-start',
        mb: 2
      }}>
        <Paper
          elevation={0}
          sx={{
            maxWidth: '70%',
            p: 2,
            borderRadius: 3,
            background: isUser 
              ? 'linear-gradient(135deg, #4c82f7, #3d6fd6)'
              : '#1a1a1a',
            border: isUser ? 'none' : '1px solid #2a2a2a',
            color: 'white'
          }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
            <Avatar
              sx={{
                width: 24,
                height: 24,
                mr: 1,
                background: getMessageTypeColor(),
                fontSize: 12
              }}
            >
              {getMessageIcon()}
            </Avatar>
            <Typography variant="caption" sx={{ color: '#b3b3b3' }}>
              {isUser ? 'You' : 'Aiden'}
              {message.input_type === 'voice' && ' (Voice)'}
            </Typography>
            <Typography variant="caption" sx={{ color: '#888', ml: 1 }}>
              {formatDistanceToNow(new Date(message.timestamp), { addSuffix: true })}
            </Typography>
          </Box>
          
          <Typography variant="body1" sx={{ 
            lineHeight: 1.5,
            wordBreak: 'break-word'
          }}>
            {typeof message.text === 'object' ? JSON.stringify(message.text) : String(message.text || '')}
          </Typography>

          {!isUser && message.message_type && (
            <Chip
              size="small"
              label={typeof message.message_type === 'object' ? JSON.stringify(message.message_type) : String(message.message_type || 'message')}
              sx={{
                mt: 1,
                background: getMessageTypeColor(),
                color: 'white',
                fontSize: '0.7rem',
                height: 20
              }}
            />
          )}
        </Paper>
      </Box>
    </motion.div>
  );
};

const TypingIndicator = () => (
  <motion.div
    initial={{ opacity: 0, y: 10 }}
    animate={{ opacity: 1, y: 0 }}
    exit={{ opacity: 0, y: -10 }}
    className="typing-indicator"
  >
    <Avatar sx={{ width: 24, height: 24, mr: 1, background: '#4c82f7' }}>
      <SmartToy sx={{ fontSize: 12 }} />
    </Avatar>
    <Typography variant="caption" sx={{ mr: 2 }}>Aiden is thinking...</Typography>
    <div className="typing-dot"></div>
    <div className="typing-dot"></div>
    <div className="typing-dot"></div>
  </motion.div>
);

const VoiceChat = ({ socket, messages, isListening, conversationActive, isConnected }) => {
  const [inputMessage, setInputMessage] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState('idle'); // idle, listening, speaking, processing
  const [isSpeaking, setIsSpeaking] = useState(false);
  const messagesEndRef = useRef(null);
  const messagesContainerRef = useRef(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (messagesContainerRef.current) {
      // Scroll only the messages container, not the entire page
      messagesContainerRef.current.scrollTop = messagesContainerRef.current.scrollHeight;
    }
  }, [messages]);

  // Handle typing indicator
  useEffect(() => {
    if (isListening || conversationActive) {
      setIsTyping(true);
      const timer = setTimeout(() => setIsTyping(false), 2000);
      return () => clearTimeout(timer);
    } else {
      setIsTyping(false);
    }
  }, [isListening, conversationActive]);

  // Listen for voice status updates
  useEffect(() => {
    if (socket) {
      const handleVoiceStatus = (data) => {
        setVoiceStatus(data.status || 'idle');
        setIsSpeaking(data.speaking || false);
      };

      socket.on('voice_status', handleVoiceStatus);
      
      return () => {
        socket.off('voice_status', handleVoiceStatus);
      };
    }
  }, [socket]);

  const handleSendMessage = async () => {
    if (!inputMessage.trim() || !isConnected) return;

    try {
      const response = await fetch('/api/conversation/send', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ message: inputMessage }),
      });

      if (response.ok) {
        setInputMessage('');
      } else {
        console.error('Failed to send message');
      }
    } catch (error) {
      console.error('Error sending message:', error);
    }
  };

  const handleKeyPress = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSendMessage();
    }
  };

  const handleStartVoice = () => {
    if (socket && !isListening) {
      socket.emit('start_voice');
    }
  };

  return (
    <Card sx={{ 
      height: '80vh', 
      display: 'flex', 
      flexDirection: 'column',
      background: '#1a1a1a',
      border: '1px solid #2a2a2a'
    }}>
      {/* Header */}
      <CardContent sx={{ 
        borderBottom: '1px solid #2a2a2a',
        pb: 2,
        background: 'linear-gradient(135deg, #1a1a1a, #2a2a2a)'
      }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Box>
            <Typography variant="h6" sx={{ fontWeight: 600 }}>
              Voice Chat with Aiden
            </Typography>
            <Typography variant="body2" sx={{ 
              color: '#b3b3b3',
              display: 'flex',
              alignItems: 'center',
              gap: 1
            }}>
              {voiceStatus === 'listening' ? (
                                 <Box sx={{ 
                   display: 'flex', 
                   alignItems: 'center', 
                   gap: 0.5,
                   background: 'linear-gradient(45deg, #4ade80, #22c55e)',
                   px: 1.5,
                   py: 0.5,
                   borderRadius: 2,
                   boxShadow: '0 0 20px rgba(74, 222, 128, 0.3)',
                   '@keyframes pulse': pulseKeyframes,
                   animation: 'pulse 1.5s infinite'
                 }}>
                   <Box sx={{ 
                     width: 8, 
                     height: 8, 
                     borderRadius: '50%', 
                     background: '#ffffff',
                     '@keyframes pulse': pulseKeyframes,
                     animation: 'pulse 1s infinite'
                   }} />
                   <span style={{ color: 'white', fontWeight: 600 }}>🎤 Listening...</span>
                 </Box>
                             ) : voiceStatus === 'speaking' || isSpeaking ? (
                 <Box sx={{ 
                   display: 'flex', 
                   alignItems: 'center', 
                   gap: 0.5,
                   background: 'linear-gradient(45deg, #f7c94c, #d6a83d)',
                   px: 1.5,
                   py: 0.5,
                   borderRadius: 2,
                   boxShadow: '0 0 20px rgba(247, 201, 76, 0.3)',
                   '@keyframes pulse': pulseKeyframes,
                   animation: 'pulse 1.5s infinite'
                 }}>
                   <Box sx={{ 
                     width: 8, 
                     height: 8, 
                     borderRadius: '50%', 
                     background: '#ffffff',
                     '@keyframes pulse': pulseKeyframes,
                     animation: 'pulse 0.8s infinite'
                   }} />
                   <span style={{ color: 'white', fontWeight: 600 }}>🔊 Speaking...</span>
                 </Box>
                             ) : voiceStatus === 'processing' ? (
                 <Box sx={{ 
                   display: 'flex', 
                   alignItems: 'center', 
                   gap: 0.5,
                   background: 'linear-gradient(45deg, #4c82f7, #3d6fd6)',
                   px: 1.5,
                   py: 0.5,
                   borderRadius: 2,
                   boxShadow: '0 0 20px rgba(76, 130, 247, 0.3)',
                   '@keyframes pulse': pulseKeyframes,
                   animation: 'pulse 1.2s infinite'
                 }}>
                   <Box sx={{ 
                     width: 8, 
                     height: 8, 
                     borderRadius: '50%', 
                     background: '#ffffff',
                     '@keyframes spin': spinKeyframes,
                     animation: 'spin 1s linear infinite'
                   }} />
                   <span style={{ color: 'white', fontWeight: 600 }}>⚡ Processing...</span>
                 </Box>
              ) : conversationActive ? (
                <span className="status-online">💬 In conversation</span>
              ) : (
                <span className="status-offline">💤 Idle</span>
              )}
            </Typography>
          </Box>
          
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            {messages.length > 0 && (
              <Chip
                size="small"
                label={`${messages.length} messages`}
                sx={{ background: '#2a2a2a', color: '#b3b3b3' }}
              />
            )}
            <Chip
              size="small"
              label={isConnected ? 'Connected' : 'Disconnected'}
              sx={{
                background: isConnected ? '#4ade80' : '#f87171',
                color: 'white'
              }}
            />
          </Box>
        </Box>
      </CardContent>

      {/* Messages Area */}
      <Box 
        ref={messagesContainerRef}
        sx={{ 
          flex: 1, 
          overflowY: 'auto', 
          p: 2,
          background: '#0a0a0a',
          scrollBehavior: 'smooth',
          '&::-webkit-scrollbar': {
            width: '6px',
          },
          '&::-webkit-scrollbar-track': {
            background: '#1a1a1a',
          },
          '&::-webkit-scrollbar-thumb': {
            background: '#4c82f7',
            borderRadius: '3px',
          },
          '&::-webkit-scrollbar-thumb:hover': {
            background: '#3d6fd6',
          },
        }}
      >
        {messages.length === 0 ? (
          <Box sx={{ 
            display: 'flex', 
            flexDirection: 'column',
            alignItems: 'center', 
            justifyContent: 'center',
            height: '100%',
            color: '#666'
          }}>
            <SmartToy sx={{ fontSize: 64, mb: 2, color: '#4c82f7' }} />
            <Typography variant="h6" sx={{ mb: 1 }}>
              Welcome to Aiden!
            </Typography>
            <Typography variant="body2" sx={{ textAlign: 'center', maxWidth: 400 }}>
              Start a conversation by pressing the voice button or typing a message below.
              You can also use the hotkey (*) to activate voice mode.
            </Typography>
          </Box>
        ) : (
          <>
            <AnimatePresence>
              {messages.map((message) => (
                <MessageBubble
                  key={message.id}
                  message={message}
                  isUser={message.type === 'user'}
                  socket={socket}
                />
              ))}
            </AnimatePresence>
            
            <AnimatePresence>
              {isTyping && <TypingIndicator />}
            </AnimatePresence>
          </>
        )}
        <div ref={messagesEndRef} />
      </Box>

      <Divider sx={{ borderColor: '#2a2a2a' }} />

      {/* Input Area */}
      <CardContent sx={{ pt: 2 }}>
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'end' }}>
          <TextField
            fullWidth
            multiline
            maxRows={3}
            placeholder={isConnected ? "Type a message or use voice..." : "Connecting..."}
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            onKeyPress={handleKeyPress}
            disabled={!isConnected}
            variant="outlined"
            sx={{
              '& .MuiOutlinedInput-root': {
                background: '#2a2a2a',
                borderRadius: 2,
                '& fieldset': {
                  borderColor: '#3a3a3a',
                },
                '&:hover fieldset': {
                  borderColor: '#4c82f7',
                },
                '&.Mui-focused fieldset': {
                  borderColor: '#4c82f7',
                },
              },
              '& .MuiInputBase-input': {
                color: 'white',
              }
            }}
          />
          
          <IconButton
            onClick={handleSendMessage}
            disabled={!inputMessage.trim() || !isConnected}
            sx={{
              background: inputMessage.trim() && isConnected 
                ? 'linear-gradient(45deg, #4c82f7, #3d6fd6)' 
                : '#2a2a2a',
              color: 'white',
              '&:hover': {
                background: inputMessage.trim() && isConnected
                  ? 'linear-gradient(45deg, #3d6fd6, #2563eb)'
                  : '#3a3a3a',
              },
              transition: 'all 0.2s ease-in-out'
            }}
          >
            <Send />
          </IconButton>
          
          <IconButton
            onClick={handleStartVoice}
            disabled={!isConnected || isListening}
            sx={{
              background: isConnected && !isListening
                ? 'linear-gradient(45deg, #f7c94c, #d6a83d)'
                : '#2a2a2a',
              color: 'white',
              '&:hover': {
                background: isConnected && !isListening
                  ? 'linear-gradient(45deg, #d6a83d, #b8940f)'
                  : '#3a3a3a',
              },
              transition: 'all 0.2s ease-in-out'
            }}
          >
            <Mic />
          </IconButton>
        </Box>
        
        <Typography variant="caption" sx={{ color: '#666', mt: 1, display: 'block' }}>
          Press Enter to send • Voice activation with * key
        </Typography>
      </CardContent>
    </Card>
  );
};

export default VoiceChat; 