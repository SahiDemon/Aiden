import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  ButtonGroup,
  Chip,
  Grid,
  Paper,
  Alert,
  CircularProgress
} from '@mui/material';
import { 
  Power, 
  PowerOff, 
  Refresh,
  Air,
  WifiOff,
  CheckCircle,
  Error
} from '@mui/icons-material';
import { motion } from 'framer-motion';
import { toast } from 'react-hot-toast';

const FanControl = ({ socket, isConnected }) => {
  const [fanStatus, setFanStatus] = useState({
    connected: false,
    ip_address: '',
    loading: false
  });
  const [actionLoading, setActionLoading] = useState(null);
  const [detailedStatus, setDetailedStatus] = useState(null);
  const [showDiagnostics, setShowDiagnostics] = useState(false);
  const [testResults, setTestResults] = useState({});

  // Fetch ESP32 status
  useEffect(() => {
    fetchFanStatus();
    // Refresh status every 30 seconds (reduced frequency)
    const interval = setInterval(fetchFanStatus, 200000);
    return () => clearInterval(interval);
  }, []);

  const fetchFanStatus = async () => {
    try {
      setFanStatus(prev => ({ ...prev, loading: true }));
      const response = await fetch('/api/esp32/status');
      const data = await response.json();
      setFanStatus({
        connected: data.connected,
        ip_address: data.ip_address,
        loading: false,
        error: data.error || null
      });
      
      // Show more detailed status info (only log, no notifications for automatic checks)
      if (data.connected) {
        console.log('ESP32 fan is connected and reachable');
      } else {
        console.log('ESP32 fan connection check failed:', data.error || 'Unknown reason');
      }
    } catch (error) {
      console.error('Error fetching fan status:', error);
      setFanStatus(prev => ({ 
        ...prev, 
        connected: false, 
        loading: false,
        error: 'Network error'
      }));
    }
  };

  const fetchDetailedStatus = async () => {
    try {
      const response = await fetch('/api/esp32/detailed-status');
      const data = await response.json();
      setDetailedStatus(data);
    } catch (error) {
      console.error('Error fetching detailed status:', error);
    }
  };

  const runTest = async (testType) => {
    setTestResults(prev => ({ ...prev, [testType]: { loading: true } }));
    
    try {
      const response = await fetch('/api/esp32/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ test_type: testType })
      });
      
      const data = await response.json();
      setTestResults(prev => ({ 
        ...prev, 
        [testType]: { 
          loading: false, 
          result: data.result,
          message: data.message,
          success: data.success
        }
      }));
      
      if (data.success && data.result) {
        toast.success(`${testType} test passed!`);
      } else {
        toast.error(`${testType} test failed: ${data.message}`);
      }
    } catch (error) {
      setTestResults(prev => ({ 
        ...prev, 
        [testType]: { 
          loading: false, 
          result: false, 
          message: error.message,
          success: false
        }
      }));
      toast.error(`${testType} test error: ${error.message}`);
    }
  };

  const handleFanControl = async (action) => {
    if (!isConnected || !fanStatus.connected) {
      toast.error('Fan not connected!');
      return;
    }

    setActionLoading(action);
    
    try {
      const response = await fetch('/api/esp32/control', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ action }),
      });

      const data = await response.json();
      
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
        toast.error(data.message || 'Fan control failed');
      }
    } catch (error) {
      console.error('Error controlling fan:', error);
      toast.error('Failed to control fan');
    } finally {
      setActionLoading(null);
    }
  };

  const getStatusColor = () => {
    if (fanStatus.loading) return '#666';
    return fanStatus.connected ? '#4ade80' : '#f87171';
  };

  const getStatusIcon = () => {
    if (fanStatus.loading) return <CircularProgress size={16} />;
    return fanStatus.connected ? <CheckCircle /> : <Error />;
  };

  return (
    <Card sx={{ 
      background: '#1a1a1a',
      border: '1px solid #2a2a2a',
      height: 'fit-content'
    }}>
      <CardContent>
        {/* Header */}
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Air sx={{ color: '#4c82f7', fontSize: 28 }} />
            <Typography variant="h6" sx={{ fontWeight: 600 }}>
              Fan Control
            </Typography>
          </Box>
          
          <Button
            size="small"
            onClick={fetchFanStatus}
            disabled={fanStatus.loading}
            sx={{ 
              minWidth: 'auto',
              color: '#b3b3b3',
              '&:hover': { background: '#2a2a2a' }
            }}
          >
            <Refresh sx={{ fontSize: 18 }} />
          </Button>
        </Box>

        {/* Status Display */}
        <Paper sx={{ 
          p: 2, 
          mb: 3, 
          background: '#2a2a2a',
          border: '1px solid #3a3a3a'
        }}>
          <Grid container spacing={2} alignItems="center">
            <Grid item>
              <motion.div
                animate={{ 
                  scale: fanStatus.connected ? [1, 1.2, 1] : 1,
                  color: getStatusColor()
                }}
                transition={{ 
                  duration: 2, 
                  repeat: fanStatus.connected ? Infinity : 0
                }}
              >
                {getStatusIcon()}
              </motion.div>
            </Grid>
            <Grid item xs>
              <Typography variant="body2" sx={{ fontWeight: 500 }}>
                {fanStatus.loading ? 'Checking connection...' : 
                 fanStatus.connected ? 'Fan Connected' : 'Fan Disconnected'}
              </Typography>
              <Typography variant="caption" sx={{ color: '#888' }}>
                IP: {fanStatus.ip_address}
              </Typography>
            </Grid>
            <Grid item>
              <Chip
                size="small"
                label={fanStatus.connected ? 'Online' : 'Offline'}
                sx={{
                  background: getStatusColor(),
                  color: 'white',
                  fontWeight: 500
                }}
              />
            </Grid>
          </Grid>
        </Paper>

        {/* Diagnostics Panel */}
        {!fanStatus.connected && (
          <Paper sx={{ 
            p: 2, 
            mb: 3, 
            background: 'rgba(247, 201, 76, 0.1)',
            border: '1px solid rgba(247, 201, 76, 0.3)'
          }}>
            <Alert 
              severity="warning" 
              sx={{ 
                background: 'transparent',
                color: '#f7c94c',
                '& .MuiAlert-icon': { color: '#f7c94c' },
                mb: 2
              }}
            >
              ESP32 fan is not connected. Check your network connection and ESP32 device.
            </Alert>
            
            {/* Manual Testing Controls */}
            <Typography variant="subtitle2" sx={{ mb: 2, color: '#f7c94c', fontWeight: 600 }}>
              Manual Diagnostics
            </Typography>
            
            <Grid container spacing={1} sx={{ mb: 2 }}>
              <Grid item xs={4}>
                <Button
                  fullWidth
                  size="small"
                  variant="outlined"
                  onClick={() => runTest('ping')}
                  disabled={testResults.ping?.loading}
                  sx={{ 
                    borderColor: '#f7c94c', 
                    color: '#f7c94c',
                    '&:hover': { borderColor: '#d6a83d', background: 'rgba(247, 201, 76, 0.1)' }
                  }}
                >
                  {testResults.ping?.loading ? <CircularProgress size={16} /> : 'Ping'}
                </Button>
              </Grid>
              <Grid item xs={4}>
                <Button
                  fullWidth
                  size="small"
                  variant="outlined"
                  onClick={() => runTest('connectivity')}
                  disabled={testResults.connectivity?.loading}
                  sx={{ 
                    borderColor: '#f7c94c', 
                    color: '#f7c94c',
                    '&:hover': { borderColor: '#d6a83d', background: 'rgba(247, 201, 76, 0.1)' }
                  }}
                >
                  {testResults.connectivity?.loading ? <CircularProgress size={16} /> : 'HTTP'}
                </Button>
              </Grid>
              <Grid item xs={4}>
                <Button
                  fullWidth
                  size="small"
                  variant="outlined"
                  onClick={() => {
                    setShowDiagnostics(!showDiagnostics);
                    if (!showDiagnostics) fetchDetailedStatus();
                  }}
                  sx={{ 
                    borderColor: '#f7c94c', 
                    color: '#f7c94c',
                    '&:hover': { borderColor: '#d6a83d', background: 'rgba(247, 201, 76, 0.1)' }
                  }}
                >
                  Details
                </Button>
              </Grid>
            </Grid>

            {/* Test Results */}
            {Object.keys(testResults).length > 0 && (
              <Box sx={{ mb: 2 }}>
                {Object.entries(testResults).map(([testType, result]) => (
                  <Typography 
                    key={testType} 
                    variant="caption" 
                    sx={{ 
                      display: 'block',
                      color: result.result ? '#4ade80' : '#f87171',
                      mb: 0.5
                    }}
                  >
                    {testType}: {result.message || (result.result ? 'Success' : 'Failed')}
                  </Typography>
                ))}
              </Box>
            )}

            {/* Detailed Diagnostics */}
            {showDiagnostics && detailedStatus && (
              <Box sx={{ 
                mt: 2, 
                p: 2, 
                background: '#1a1a1a', 
                borderRadius: 1,
                border: '1px solid #3a3a3a'
              }}>
                <Typography variant="caption" sx={{ color: '#b3b3b3', display: 'block', mb: 1 }}>
                  ESP32 Diagnostics:
                </Typography>
                <Typography variant="caption" sx={{ color: '#888', display: 'block' }}>
                  IP: {detailedStatus.ip_address}
                </Typography>
                <Typography variant="caption" sx={{ color: '#888', display: 'block' }}>
                  Ping Test: {detailedStatus.ping_test ? '✅' : '❌'}
                </Typography>
                <Typography variant="caption" sx={{ color: '#888', display: 'block' }}>
                  Endpoints Tested: {detailedStatus.endpoints_tested?.length || 0}
                </Typography>
                {detailedStatus.error && (
                  <Typography variant="caption" sx={{ color: '#f87171', display: 'block' }}>
                    Error: {detailedStatus.error}
                  </Typography>
                )}
              </Box>
            )}
          </Paper>
        )}

        {/* Control Buttons */}
        {fanStatus.connected && (
          <Grid container spacing={2}>
            {/* Primary Controls */}
            <Grid item xs={6}>
              <Button
                fullWidth
                variant="contained"
                size="large"
                onClick={() => handleFanControl('turn_on')}
                disabled={!isConnected || actionLoading === 'turn_on'}
                startIcon={actionLoading === 'turn_on' ? 
                  <CircularProgress size={16} /> : <Power />}
                sx={{
                  background: 'linear-gradient(45deg, #4ade80, #22c55e)',
                  '&:hover': {
                    background: 'linear-gradient(45deg, #22c55e, #16a34a)',
                  },
                  py: 1.5,
                  fontWeight: 600
                }}
              >
                Turn On
              </Button>
            </Grid>
            
            <Grid item xs={6}>
              <Button
                fullWidth
                variant="contained"
                size="large"
                onClick={() => handleFanControl('turn_off')}
                disabled={!isConnected || actionLoading === 'turn_off'}
                startIcon={actionLoading === 'turn_off' ? 
                  <CircularProgress size={16} /> : <PowerOff />}
                sx={{
                  background: 'linear-gradient(45deg, #f87171, #ef4444)',
                  '&:hover': {
                    background: 'linear-gradient(45deg, #ef4444, #dc2626)',
                  },
                  py: 1.5,
                  fontWeight: 600
                }}
              >
                Turn Off
              </Button>
            </Grid>

            {/* Mode Control */}
            <Grid item xs={12}>
              <Button
                fullWidth
                variant="outlined"
                size="large"
                onClick={() => handleFanControl('change_mode')}
                disabled={!isConnected || actionLoading === 'change_mode'}
                startIcon={actionLoading === 'change_mode' ? 
                  <CircularProgress size={16} /> : <Refresh />}
                sx={{
                  borderColor: '#4c82f7',
                  color: '#4c82f7',
                  '&:hover': {
                    borderColor: '#3d6fd6',
                    background: 'rgba(76, 130, 247, 0.1)',
                  },
                  py: 1.5,
                  fontWeight: 600
                }}
              >
                Change Mode
              </Button>
            </Grid>
          </Grid>
        )}

        {/* Help Text */}
        <Typography variant="caption" sx={{ 
          color: '#666', 
          mt: 2, 
          display: 'block',
          textAlign: 'center'
        }}>
          You can also control the fan using voice commands like "turn on the fan" or "change fan mode"
        </Typography>
      </CardContent>
    </Card>
  );
};

export default FanControl; 