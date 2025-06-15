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

// Custom Fan Icon Component
const FanIcon = ({ color = '#4c82f7', size = 28, className = '' }) => (
  <svg 
    width={size} 
    height={size} 
    viewBox="0 0 1024 1024" 
    className={className}
    style={{ color }}
  >
    <path d="M386.439 494.505c0 69.22 56.328 125.549 125.549 125.549 69.22 0 125.549-56.329 125.549-125.549s-56.329-125.549-125.549-125.549c-69.221 0-125.549 56.329-125.549 125.549z" fill={color} />
    <path d="M526.141 369.81c37.32 21.788 62.521 62.166 62.521 108.406 0 69.22-56.327 125.546-125.548 125.546-4.791 0-9.502-0.326-14.154-0.851 18.55 10.827 40.044 17.142 63.026 17.142 69.22 0 125.549-56.326 125.549-125.546 0.002-64.432-48.819-117.632-111.394-124.697z" fill="#070707" />
    <path d="M689.137 83.039c-8.864-3.822-19.198 0-23.295 8.755l-91.57 194.666c-2.103 4.52-2.243 9.423-0.421 14.048 1.859 4.623 5.535 7.776 10.159 9.599 82.813 32.367 133.746 115.738 123.866 204.085-0.523 4.939 0.984 7.988 4.205 11.769 3.224 3.784 7.883 2.21 12.823 2.453l215.015 1.962h0.839c9.284 0 17.097 0.42 17.868-8.931 14.958-191.129-93.322-362.74-269.489-438.406zM313.961 540.044a17.824 17.824 0 0 0 3.505-13.836c-14.399-87.751 32.123-174.592 113.112-211.199 4.552-2.065 7.985-5.885 9.599-10.577 1.61-4.697 1.19-9.88-1.159-14.224L337.572 100.447c-4.552-8.545-15.099-11.909-23.714-7.67C141.787 177.445 42.93 362.02 67.803 552.097c1.191 9.035 8.864 15.622 17.76 15.622 0.596 0 1.154-0.036 1.717-0.069l214.177-20.669a17.987 17.987 0 0 0 12.504-6.937zM657.646 655.294a17.832 17.832 0 0 0-11.981-7.742 17.948 17.948 0 0 0-13.872 3.469c-68.205 52.337-171.371 52.368-239.608 0-3.923-3.049-9.039-4.275-13.839-3.469a17.962 17.962 0 0 0-12.012 7.742l-119.386 179.04c-5.323 8.057-3.361 18.882 4.483 24.52 76.297 54.683 166.396 83.584 260.557 83.584 94.162 0 184.259-28.901 260.557-83.584 7.846-5.639 9.806-16.464 4.484-24.52l-119.383-179.04z" fill="#152B3C" />
    <path d="M697.398 86.959c151.712 83.295 242.407 242.383 228.646 418.195-0.772 9.35-8.583 8.933-17.866 8.933h-0.839l-199.329-1.819c-0.066 0.641-0.063 1.277-0.134 1.922-0.523 4.94 0.986 7.991 4.205 11.769 3.223 3.786 7.885 2.212 12.825 2.458l215.014 1.961h0.839c9.283 0 17.094 0.417 17.866-8.933 14.72-188.066-90.037-357.025-261.227-434.486zM439.019 290.209L337.572 100.446c-4.552-8.543-15.099-11.908-23.714-7.668-1.13 0.557-2.176 1.226-3.302 1.79l95.881 179.351c2.35 4.343 2.767 9.526 1.159 14.223-1.615 4.694-5.047 8.512-9.599 10.58-80.989 36.603-127.511 123.447-113.114 211.197a17.806 17.806 0 0 1-3.503 13.834 17.992 17.992 0 0 1-12.505 6.939l-201.251 19.42c0.084 0.664 0.094 1.32 0.179 1.985 1.19 9.036 8.864 15.623 17.759 15.623 0.597 0 1.156-0.04 1.719-0.072l214.175-20.666a17.993 17.993 0 0 0 12.505-6.939 17.812 17.812 0 0 0 3.504-13.834c-14.397-87.75 32.125-174.593 113.114-211.196a18.005 18.005 0 0 0 9.599-10.58c1.608-4.697 1.191-9.88-1.159-14.224z" fill="#070707" />
    <path d="M405.263 660.152a178.395 178.395 0 0 1-13.077-9.132c-3.706-2.879-8.473-3.986-13.038-3.436a189.087 189.087 0 0 0 26.115 12.568z" fill="#3F67A6" />
    <path d="M777.029 834.333l-119.383-179.04a17.829 17.829 0 0 0-11.98-7.74c-4.514-0.748-9.093 0.426-12.899 2.999l111.68 167.491c5.324 8.058 3.36 18.885-4.485 24.523-76.297 54.68-166.394 83.584-260.557 83.584-63.956 0-125.919-13.643-183.077-39.331 65.805 36.319 139.327 55.622 215.658 55.622 94.162 0 184.259-28.903 260.557-83.583 7.847-5.641 9.809-16.468 4.486-24.525z" fill="#070707" />
  </svg>
);

const FanControl = ({ socket, isConnected }) => {
  const [fanStatus, setFanStatus] = useState({
    connected: false,
    ip_address: '',
    loading: false
  });
  const [fanState, setFanState] = useState({
    state: 'unknown',
    speed: 'unknown',
    human_readable: 'Checking fan status...',
    loading: false
  });
  const [actionLoading, setActionLoading] = useState(null);
  const [detailedStatus, setDetailedStatus] = useState(null);
  const [showDiagnostics, setShowDiagnostics] = useState(false);
  const [testResults, setTestResults] = useState({});

  // Fetch ESP32 status
  useEffect(() => {
    fetchFanStatus();
    fetchFanState();
    // Refresh status every 30 seconds (reduced frequency)
    const interval = setInterval(() => {
      fetchFanStatus();
      fetchFanState();
    }, 30000);
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

  const fetchFanState = async () => {
    try {
      setFanState(prev => ({ ...prev, loading: true }));
      const response = await fetch('/api/esp32/smart-status');
      const data = await response.json();
      
      if (data.success) {
        setFanState({
          state: data.parsed?.state || 'unknown',
          speed: data.parsed?.speed || 'unknown',
          human_readable: data.human_readable || 'Status unavailable',
          loading: false,
          error: null
        });
      } else {
        setFanState({
          state: 'unknown',
          speed: 'unknown',
          human_readable: data.error || 'Unable to get fan status',
          loading: false,
          error: data.error
        });
      }
    } catch (error) {
      console.error('Error fetching fan state:', error);
      setFanState({
        state: 'unknown',
        speed: 'unknown',
        human_readable: 'Error getting fan status',
        loading: false,
        error: error.message
      });
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
        
        // Refresh fan state after successful action
        setTimeout(() => {
          fetchFanState();
        }, 1000); // Wait 1 second for ESP32 to update
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

  const refreshFanStatus = async () => {
    await Promise.all([fetchFanStatus(), fetchFanState()]);
    toast.success('Fan status refreshed', {
      icon: '🔄',
      duration: 2000,
      style: {
        background: '#1a1a1a',
        color: '#fff',
        border: '1px solid #4ade80'
      }
    });
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
            <FanIcon color={'#4c82f7'} size={28} />
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

        {/* Fan Status Display */}
        <Paper sx={{ 
          p: 2, 
          mb: 3, 
          background: '#2a2a2a',
          border: '1px solid #3a3a3a'
        }}>
          <Typography variant="h6" sx={{ mb: 2, color: '#fff', fontWeight: 600 }}>
            Current Fan Status
          </Typography>
          
          <Grid container spacing={2} alignItems="center">
            <Grid item>
              <motion.div
                animate={{ 
                  rotate: fanState.state === 'on' ? 360 : 0,
                  scale: fanState.loading ? [1, 1.1, 1] : 1
                }}
                transition={{ 
                  rotate: { duration: 2, repeat: fanState.state === 'on' ? Infinity : 0, ease: "linear" },
                  scale: { duration: 1, repeat: fanState.loading ? Infinity : 0 }
                }}
              >
                <FanIcon 
                  color={fanState.state === 'on' ? '#4ade80' : 
                         fanState.state === 'off' ? '#f87171' : '#888'} 
                  size={32}
                />
              </motion.div>
            </Grid>
            <Grid item xs>
              <Typography variant="body1" sx={{ fontWeight: 500, color: '#fff' }}>
                {fanState.loading ? 'Checking status...' : fanState.human_readable}
              </Typography>
              {fanState.state !== 'unknown' && !fanState.loading && (
                <Typography variant="caption" sx={{ color: '#888', display: 'block' }}>
                  State: {fanState.state} {fanState.speed !== 'unknown' && fanState.speed !== '0' && `• Speed: ${fanState.speed}`}
                </Typography>
              )}
            </Grid>
            <Grid item>
              <Button
                size="small"
                variant="outlined"
                onClick={refreshFanStatus}
                disabled={fanState.loading || fanStatus.loading}
                sx={{
                  borderColor: '#4ade80',
                  color: '#4ade80',
                  '&:hover': {
                    borderColor: '#22c55e',
                    background: 'rgba(34, 197, 94, 0.1)'
                  }
                }}
              >
                <Refresh sx={{ mr: 1, fontSize: 16 }} />
                Refresh
              </Button>
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