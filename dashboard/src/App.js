import React, { useState, useEffect } from 'react';
import { 
  Box, 
  Grid, 
  AppBar, 
  Toolbar, 
  Typography, 
  IconButton,
  Badge,
  Tooltip
} from '@mui/material';
import { 
  Mic, 
  MicOff, 
  Settings, 
  Power,
  Wifi,
  WifiOff,
  Refresh,
  Chat
} from '@mui/icons-material';
import { motion, AnimatePresence } from 'framer-motion';
import { Toaster, toast } from 'react-hot-toast';
import io from 'socket.io-client';

import VoiceChat from './components/VoiceChat';
import FanControl from './components/FanControl';
import SystemStatus from './components/SystemStatus';
import ConfigPanel from './components/ConfigPanel';
import VoiceVisualizer from './components/VoiceVisualizer';


function App() {
  const [socket, setSocket] = useState(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [conversationActive, setConversationActive] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [systemStatus, setSystemStatus] = useState({
    status: 'offline',
    components: {}
  });
  const [messages, setMessages] = useState([]);

  useEffect(() => {
    // Connect to Socket.IO server
    const newSocket = io('http://localhost:5000');
    setSocket(newSocket);

    // Connection event handlers
    newSocket.on('connect', () => {
      setIsConnected(true);
      toast.success('Connected to Aiden!', {
        style: {
          background: '#1a1a1a',
          color: '#fff',
          border: '1px solid #4c82f7'
        }
      });
    });

    newSocket.on('disconnect', () => {
      setIsConnected(false);
      setIsListening(false);
      setConversationActive(false);
      toast.error('Disconnected from Aiden', {
        style: {
          background: '#1a1a1a',
          color: '#fff',
          border: '1px solid #f87171'
        }
      });
    });

    // Voice status updates
    newSocket.on('voice_status', (data) => {
      setIsListening(data.listening);
      setConversationActive(data.conversation_active);
    });

    // New messages
    newSocket.on('new_message', (message) => {
      setMessages(prev => [...prev, message]);
    });

    // Hotkey activation
    newSocket.on('hotkey_activated', (data) => {
      toast.success('Voice activated via hotkey!', {
        icon: '🎤',
        style: {
          background: '#1a1a1a',
          color: '#fff',
          border: '1px solid #4c82f7'
        }
      });
    });

    // Command execution
    newSocket.on('command_executed', (data) => {
      toast.success(`Command executed: ${data.command.action}`, {
        style: {
          background: '#1a1a1a',
          color: '#fff',
          border: '1px solid #4ade80'
        }
      });
    });

    // ESP32 actions
    newSocket.on('esp32_action', (data) => {
      if (data.success) {
        toast.success(data.message, {
          icon: '🌀',
          style: {
            background: '#1a1a1a',
            color: '#fff',
            border: '1px solid #4ade80'
          }
        });
      } else {
        toast.error(`ESP32 Error: ${data.message}`, {
          style: {
            background: '#1a1a1a',
            color: '#fff',
            border: '1px solid #f87171'
          }
        });
      }
    });

    // Action results from action card clicks
    newSocket.on('action_result', (data) => {
      if (data.success) {
        toast.success(data.message, {
          icon: '✅',
          style: {
            background: '#1a1a1a',
            color: '#fff',
            border: '1px solid #4ade80'
          }
        });
      } else {
        toast.error(data.message, {
          icon: '❌',
          style: {
            background: '#1a1a1a',
            color: '#fff',
            border: '1px solid #f87171'
          }
        });
      }
    });

    // Cleanup
    return () => {
      newSocket.close();
    };
  }, []);

  // Fetch system status
  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const response = await fetch('/api/status');
        const data = await response.json();
        setSystemStatus(data);
        setIsListening(data.listening);
        setConversationActive(data.conversation_active);
      } catch (error) {
        console.error('Error fetching status:', error);
      }
    };

    // Fetch status immediately and then every 5 seconds
    fetchStatus();
    const interval = setInterval(fetchStatus, 5000);

    return () => clearInterval(interval);
  }, []);

  const handleStartVoice = () => {
    if (socket && !isListening) {
      socket.emit('start_voice');
    }
  };

  const handleStopVoice = () => {
    if (socket && isListening) {
      socket.emit('stop_voice');
    }
  };

  const handleNewSession = () => {
    // Clear messages
    setMessages([]);
    
    // Notify backend to clear conversation history
    if (socket) {
      socket.emit('clear_conversation');
    }

    toast.success('New session started!', {
      icon: '🆕',
      style: {
        background: '#1a1a1a',
        color: '#fff',
        border: '1px solid #4ade80'
      }
    });
  };



  return (
    <Box sx={{ 
      minHeight: '100vh', 
      background: 'linear-gradient(135deg, #0a0a0a 0%, #1a1a1a 100%)',
      display: 'flex',
      flexDirection: 'column'
    }}>
      <Toaster position="top-right" />
      
      {/* Add CSS Animation */}
      <style>
        {`
          @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
          }
        `}
      </style>
      
      {/* Header */}
      <AppBar 
        position="sticky" 
        sx={{ 
          background: 'rgba(26, 26, 26, 0.9)',
          backdropFilter: 'blur(20px)',
          borderBottom: '1px solid rgba(255, 255, 255, 0.1)'
        }}
      >
        <Toolbar sx={{ minHeight: '80px !important', py: 1 }}>
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5 }}
            style={{ display: 'flex', alignItems: 'center', gap: '16px' }}
          >
            <Box sx={{
              width: 48,
              height: 48,
              borderRadius: '12px',
              background: 'linear-gradient(135deg, #4c82f7, #6a96ff)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 8px 32px rgba(76, 130, 247, 0.3)'
            }}>
              <Chat sx={{ color: 'white', fontSize: 28 }} />
            </Box>
            <Box>
              <Typography variant="h4" component="div" sx={{ 
                fontWeight: 800,
                background: 'linear-gradient(45deg, #4c82f7, #6a96ff)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
                lineHeight: 1.2
              }}>
                Aiden AI
              </Typography>
              <Typography variant="body2" sx={{ 
                color: 'rgba(255, 255, 255, 0.7)',
                fontWeight: 500
              }}>
                Voice-Powered Assistant
              </Typography>
            </Box>
          </motion.div>

          <Box sx={{ flexGrow: 1 }} />
          
          {/* Status Indicator */}
          <Box sx={{ 
            display: 'flex', 
            alignItems: 'center', 
            gap: 1,
            background: 'rgba(255, 255, 255, 0.05)',
            borderRadius: '20px',
            px: 2,
            py: 1,
            border: '1px solid rgba(255, 255, 255, 0.1)'
          }}>
            <Box sx={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              backgroundColor: isConnected ? '#4ade80' : '#f87171',
              animation: isConnected ? 'pulse 2s infinite' : 'none'
            }} />
            <Typography variant="caption" sx={{ 
              color: 'rgba(255, 255, 255, 0.8)',
              fontWeight: 600
            }}>
              {isConnected ? 'Online' : 'Offline'}
            </Typography>
          </Box>

          {/* Voice Visualizer */}
          <AnimatePresence>
            {(isListening || conversationActive) && (
              <motion.div
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.8 }}
                transition={{ duration: 0.3 }}
              >
                <VoiceVisualizer active={isListening} />
              </motion.div>
            )}
          </AnimatePresence>

          {/* Voice Control Button */}
          <Tooltip title={isListening ? "Stop Voice" : "Start Voice"}>
            <IconButton
              onClick={isListening ? handleStopVoice : handleStartVoice}
              disabled={!isConnected}
              sx={{
                mx: 1,
                background: isListening 
                  ? 'linear-gradient(45deg, #f87171, #ef4444)' 
                  : 'linear-gradient(45deg, #4c82f7, #3d6fd6)',
                color: 'white',
                '&:hover': {
                  background: isListening 
                    ? 'linear-gradient(45deg, #ef4444, #dc2626)' 
                    : 'linear-gradient(45deg, #3d6fd6, #2563eb)',
                  transform: 'scale(1.05)'
                },
                transition: 'all 0.2s ease-in-out'
              }}
            >
              {isListening ? <MicOff /> : <Mic />}
            </IconButton>
          </Tooltip>

          {/* New Session Button */}
          <Tooltip title="Start New Session">
            <IconButton
              onClick={handleNewSession}
              sx={{
                mx: 1,
                background: 'linear-gradient(45deg, #4ade80, #22c55e)',
                color: 'white',
                '&:hover': {
                  background: 'linear-gradient(45deg, #22c55e, #16a34a)',
                  transform: 'scale(1.05)'
                },
                transition: 'all 0.2s ease-in-out'
              }}
            >
              <Refresh />
            </IconButton>
          </Tooltip>

          {/* Settings */}
          <Tooltip title="Settings">
            <IconButton
              onClick={() => setShowSettings(!showSettings)}
              sx={{ 
                color: 'rgba(255, 255, 255, 0.8)',
                '&:hover': {
                  color: 'white',
                  background: 'rgba(255, 255, 255, 0.1)'
                }
              }}
            >
              <Settings />
            </IconButton>
          </Tooltip>
        </Toolbar>
      </AppBar>

      {/* Main Content */}
      <Box sx={{ 
        flex: 1, 
        p: 3, 
        overflow: 'auto',
        height: 'calc(100vh - 80px)'
      }}>
        <Grid container spacing={3} sx={{ minHeight: '100%' }}>
          {/* Left Column - Voice Chat */}
          <Grid item xs={12} lg={8}>
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.1 }}
              style={{ height: '100%', minHeight: 'calc(100vh - 140px)' }}
            >
              <VoiceChat
                socket={socket}
                messages={messages}
                isListening={isListening}
                conversationActive={conversationActive}
                isConnected={isConnected}
              />
            </motion.div>
          </Grid>

          {/* Right Column - Controls & Status */}
          <Grid item xs={12} lg={4}>
            <Box sx={{ 
              display: 'flex', 
              flexDirection: 'column', 
              gap: 3,
              height: '100%',
              minHeight: 'calc(100vh - 140px)'
            }}>
              


              {/* System Status */}
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.5, delay: 0.3 }}
                >
                  <SystemStatus
                    socket={socket}
                    status={systemStatus}
                    isConnected={isConnected}
                    isListening={isListening}
                    conversationActive={conversationActive}
                  />
                </motion.div>

              {/* Fan Control */}
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.5, delay: 0.4 }}
                >
                  <FanControl socket={socket} isConnected={isConnected} />
                </motion.div>

            </Box>
          </Grid>
        </Grid>
      </Box>

      {/* Settings Panel */}
      <AnimatePresence>
        {showSettings && (
          <ConfigPanel 
            open={showSettings} 
            onClose={() => setShowSettings(false)}
            socket={socket}
          />
        )}
      </AnimatePresence>
    </Box>
  );
}

export default App; 