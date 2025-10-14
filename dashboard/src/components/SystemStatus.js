import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Grid,
  Chip,
  LinearProgress,
  Paper,
  Avatar,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Divider
} from '@mui/material';
import {
  SmartToy,
  Mic,
  VolumeUp,
  Psychology,
  Memory,
  Wifi,
  CheckCircle,
  Error,
  AccessTime
} from '@mui/icons-material';
import { motion } from 'framer-motion';

const SystemStatus = ({ socket, status, isConnected, isListening, conversationActive }) => {
  const [systemStats, setSystemStats] = useState({
    uptime: '0m',
    totalInteractions: 0,
    voiceInteractions: 0,
    textInteractions: 0
  });

  useEffect(() => {
    fetchSystemStats();
    const interval = setInterval(fetchSystemStats, 30000); // Update every 30 seconds
    return () => clearInterval(interval);
  }, []);

  const fetchSystemStats = async () => {
    try {
      const response = await fetch('/api/conversation/history');
      const data = await response.json();
      
      if (data.success) {
        const voiceCount = data.history.filter(h => h.text && h.text.includes('voice')).length;
        const textCount = data.history.length - voiceCount;
        
        setSystemStats({
          uptime: calculateUptime(),
          totalInteractions: data.history.length,
          voiceInteractions: voiceCount,
          textInteractions: textCount
        });
      }
    } catch (error) {
      console.error('Error fetching system stats:', error);
    }
  };

  const calculateUptime = () => {
    // Simple uptime calculation - in a real app this would come from the backend
    const now = new Date();
    const start = new Date(now.getTime() - (Math.random() * 3600000)); // Random up to 1 hour
    const diff = now - start;
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(minutes / 60);
    
    if (hours > 0) {
      return `${hours}h ${minutes % 60}m`;
    }
    return `${minutes}m`;
  };

  const getComponentStatus = (component) => {
    const componentStatus = status.components?.[component];
    return componentStatus !== undefined ? componentStatus : false;
  };

  const getStatusColor = (isOnline) => {
    return isOnline ? '#4ade80' : '#f87171';
  };

  const getConnectionQuality = () => {
    if (!isConnected) return { level: 0, label: 'Disconnected', color: '#f87171' };
    if (isListening) return { level: 100, label: 'Excellent', color: '#4ade80' };
    if (conversationActive) return { level: 80, label: 'Good', color: '#4c82f7' };
    return { level: 60, label: 'Fair', color: '#f7c94c' };
  };

  const connectionQuality = getConnectionQuality();

  const systemComponents = [
    { name: 'Voice System', key: 'voice_system', icon: VolumeUp },
    { name: 'Speech Recognition', key: 'stt_system', icon: Mic },
    { name: 'LLM Connector', key: 'llm_connector', icon: Psychology },
    { name: 'ESP32 Controller', key: 'esp32_controller', icon: Wifi }
  ];

  return (
    <Card sx={{ 
      background: '#1a1a1a',
      border: '1px solid #2a2a2a',
      height: 'fit-content'
    }}>
      <CardContent>
        {/* Header */}
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
          <SmartToy sx={{ color: '#4c82f7', fontSize: 28, mr: 1 }} />
          <Typography variant="h6" sx={{ fontWeight: 600 }}>
            System Status
          </Typography>
        </Box>

        {/* Main Status */}
        <Paper sx={{ 
          p: 2, 
          mb: 2, 
          background: isConnected ? 'rgba(76, 130, 247, 0.1)' : 'rgba(248, 113, 113, 0.1)',
          border: `1px solid ${isConnected ? '#4c82f7' : '#f87171'}`
        }}>
          <Grid container alignItems="center" spacing={2}>
            <Grid item>
              <Avatar sx={{ 
                background: isConnected ? '#4c82f7' : '#f87171',
                width: 40,
                height: 40
              }}>
                {isConnected ? <CheckCircle /> : <Error />}
              </Avatar>
            </Grid>
            <Grid item xs>
              <Typography variant="h6" sx={{ fontWeight: 600 }}>
                {isConnected ? 'Aiden Online' : 'Aiden Offline'}
              </Typography>
              <Typography variant="body2" sx={{ color: '#b3b3b3' }}>
                {isListening ? '🎤 Listening for commands' :
                 conversationActive ? '💬 In conversation' :
                 isConnected ? '💤 Ready and waiting' : '❌ Not connected'}
              </Typography>
            </Grid>
          </Grid>
        </Paper>

        {/* Connection Quality */}
        <Box sx={{ mb: 3 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
            <Typography variant="body2">Connection Quality</Typography>
            <Typography variant="body2" sx={{ color: connectionQuality.color }}>
              {connectionQuality.label}
            </Typography>
          </Box>
          <LinearProgress
            variant="determinate"
            value={connectionQuality.level}
            sx={{
              height: 8,
              borderRadius: 4,
              background: '#2a2a2a',
              '& .MuiLinearProgress-bar': {
                background: `linear-gradient(45deg, ${connectionQuality.color}, ${connectionQuality.color}90)`,
                borderRadius: 4
              }
            }}
          />
        </Box>

        {/* System Components */}
        <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600 }}>
          Components
        </Typography>
        <List dense sx={{ mb: 2 }}>
          {systemComponents.map((component, index) => {
            const isOnline = getComponentStatus(component.key);
            const IconComponent = component.icon;
            
            return (
              <ListItem key={index} sx={{ px: 0 }}>
                <ListItemIcon>
                  <IconComponent sx={{ 
                    color: getStatusColor(isOnline),
                    fontSize: 20 
                  }} />
                </ListItemIcon>
                <ListItemText
                  primary={component.name}
                  primaryTypographyProps={{ fontSize: '0.875rem' }}
                />
                <Chip
                  size="small"
                  label={isOnline ? 'Active' : 'Inactive'}
                  sx={{
                    background: getStatusColor(isOnline),
                    color: 'white',
                    fontSize: '0.7rem',
                    height: 20
                  }}
                />
              </ListItem>
            );
          })}
        </List>

        <Divider sx={{ borderColor: '#2a2a2a', my: 2 }} />

        {/* System Statistics */}
        <Typography variant="subtitle2" sx={{ mb: 2, fontWeight: 600 }}>
          Statistics
        </Typography>
        <Grid container spacing={2}>
          <Grid item xs={6}>
            <Paper sx={{ 
              p: 1.5, 
              textAlign: 'center',
              background: '#2a2a2a',
              border: '1px solid #3a3a3a'
            }}>
              <Typography variant="h6" sx={{ color: '#4c82f7', fontWeight: 700 }}>
                {systemStats.totalInteractions}
              </Typography>
              <Typography variant="caption" sx={{ color: '#b3b3b3' }}>
                Total Interactions
              </Typography>
            </Paper>
          </Grid>
          <Grid item xs={6}>
            <Paper sx={{ 
              p: 1.5, 
              textAlign: 'center',
              background: '#2a2a2a',
              border: '1px solid #3a3a3a'
            }}>
              <AccessTime sx={{ color: '#f7c94c', mb: 0.5 }} />
              <Typography variant="caption" sx={{ color: '#b3b3b3', display: 'block' }}>
                Uptime: {systemStats.uptime}
              </Typography>
            </Paper>
          </Grid>
        </Grid>

        {/* Voice vs Text Breakdown */}
        {systemStats.totalInteractions > 0 && (
          <Box sx={{ mt: 2 }}>
            <Typography variant="caption" sx={{ color: '#b3b3b3', mb: 1, display: 'block' }}>
              Interaction Types
            </Typography>
            <Grid container spacing={1}>
              <Grid item xs={6}>
                <Chip
                  size="small"
                  icon={<Mic sx={{ fontSize: 16 }} />}
                  label={`Voice: ${systemStats.voiceInteractions}`}
                  sx={{
                    background: '#4c82f7',
                    color: 'white',
                    fontSize: '0.7rem',
                    width: '100%'
                  }}
                />
              </Grid>
              <Grid item xs={6}>
                <Chip
                  size="small"
                  label={`Text: ${systemStats.textInteractions}`}
                  sx={{
                    background: '#f7c94c',
                    color: 'black',
                    fontSize: '0.7rem',
                    width: '100%'
                  }}
                />
              </Grid>
            </Grid>
          </Box>
        )}
      </CardContent>
    </Card>
  );
};

export default SystemStatus; 