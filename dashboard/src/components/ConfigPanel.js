import React, { useState, useEffect } from 'react';
import {
  Box,
  Drawer,
  Typography,
  IconButton,
  Tabs,
  Tab,
  TextField,
  Button,
  Switch,
  FormControlLabel,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Divider,
  Alert,
  Paper,
  Grid,
  Slider,
  Chip
} from '@mui/material';
import { Close, Save, Refresh, VolumeUp, Mic, Psychology, Settings } from '@mui/icons-material';
import { motion, AnimatePresence } from 'framer-motion';
import { toast } from 'react-hot-toast';

const TabPanel = ({ children, value, index, ...other }) => (
  <div
    role="tabpanel"
    hidden={value !== index}
    id={`config-tabpanel-${index}`}
    aria-labelledby={`config-tab-${index}`}
    {...other}
  >
    {value === index && (
      <Box sx={{ p: 3 }}>
        {children}
      </Box>
    )}
  </div>
);

const ConfigPanel = ({ open, onClose, socket }) => {
  const [tabValue, setTabValue] = useState(0);
  const [config, setConfig] = useState(null);
  const [userProfile, setUserProfile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);

  useEffect(() => {
    if (open) {
      fetchConfig();
    }
  }, [open]);

  const fetchConfig = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/config');
      const data = await response.json();
      
      if (data.success) {
        setConfig(data.config);
        setUserProfile(data.user_profile);
      } else {
        toast.error('Failed to load configuration');
      }
    } catch (error) {
      console.error('Error fetching config:', error);
      toast.error('Error loading configuration');
    } finally {
      setLoading(false);
    }
  };

  const saveConfig = async () => {
    setSaving(true);
    try {
      const response = await fetch('/api/config', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          config,
          user_profile: userProfile
        }),
      });

      const data = await response.json();
      
      if (data.success) {
        setHasChanges(false);
        toast.success('Configuration saved successfully!');
      } else {
        toast.error(data.error || 'Failed to save configuration');
      }
    } catch (error) {
      console.error('Error saving config:', error);
      toast.error('Error saving configuration');
    } finally {
      setSaving(false);
    }
  };

  const updateConfig = (path, value) => {
    setConfig(prev => {
      const newConfig = { ...prev };
      const keys = path.split('.');
      let current = newConfig;
      
      for (let i = 0; i < keys.length - 1; i++) {
        current = current[keys[i]];
      }
      current[keys[keys.length - 1]] = value;
      
      setHasChanges(true);
      return newConfig;
    });
  };

  const updateUserProfile = (path, value) => {
    setUserProfile(prev => {
      const newProfile = { ...prev };
      const keys = path.split('.');
      let current = newProfile;
      
      for (let i = 0; i < keys.length - 1; i++) {
        if (!current[keys[i]]) current[keys[i]] = {};
        current = current[keys[i]];
      }
      current[keys[keys.length - 1]] = value;
      
      setHasChanges(true);
      return newProfile;
    });
  };

  const resetToDefaults = () => {
    if (window.confirm('Reset all settings to defaults? This cannot be undone.')) {
      fetchConfig();
      setHasChanges(false);
      toast.success('Settings reset to defaults');
    }
  };

  if (!config || !userProfile) {
    return (
      <Drawer
        anchor="right"
        open={open}
        onClose={onClose}
        sx={{ '& .MuiDrawer-paper': { width: 500, background: '#1a1a1a' } }}
      >
        <Box sx={{ p: 3, display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
          <Typography>Loading configuration...</Typography>
        </Box>
      </Drawer>
    );
  }

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      sx={{ 
        '& .MuiDrawer-paper': { 
          width: 500, 
          background: '#1a1a1a',
          border: 'none'
        } 
      }}
    >
      <motion.div
        initial={{ x: 500 }}
        animate={{ x: 0 }}
        exit={{ x: 500 }}
        transition={{ duration: 0.3, ease: 'easeInOut' }}
        style={{ height: '100%' }}
      >
        {/* Header */}
        <Box sx={{ 
          p: 2, 
          borderBottom: '1px solid #2a2a2a',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between'
        }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Settings sx={{ color: '#4c82f7' }} />
            <Typography variant="h6" sx={{ fontWeight: 600 }}>
              Aiden Settings
            </Typography>
          </Box>
          
          <Box sx={{ display: 'flex', gap: 1 }}>
            {hasChanges && (
              <Button
                size="small"
                onClick={saveConfig}
                disabled={saving}
                startIcon={<Save />}
                sx={{
                  background: 'linear-gradient(45deg, #4ade80, #22c55e)',
                  color: 'white',
                  '&:hover': {
                    background: 'linear-gradient(45deg, #22c55e, #16a34a)',
                  }
                }}
              >
                {saving ? 'Saving...' : 'Save'}
              </Button>
            )}
            
            <IconButton onClick={onClose} sx={{ color: 'white' }}>
              <Close />
            </IconButton>
          </Box>
        </Box>

        {/* Status Alert */}
        <AnimatePresence>
          {hasChanges && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
            >
              <Alert 
                severity="info"
                sx={{ 
                  m: 2,
                  background: 'rgba(76, 130, 247, 0.1)',
                  border: '1px solid rgba(76, 130, 247, 0.3)',
                  color: '#4c82f7'
                }}
              >
                You have unsaved changes. Click Save to apply them.
              </Alert>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Tabs */}
        <Box sx={{ borderBottom: '1px solid #2a2a2a' }}>
          <Tabs
            value={tabValue}
            onChange={(e, newValue) => setTabValue(newValue)}
            textColor="primary"
            indicatorColor="primary"
          >
            <Tab label="Voice" icon={<VolumeUp />} />
            <Tab label="Recognition" icon={<Mic />} />
            <Tab label="AI" icon={<Psychology />} />
            <Tab label="Profile" icon={<Settings />} />
          </Tabs>
        </Box>

        {/* Voice Settings */}
        <TabPanel value={tabValue} index={0}>
          <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
            Voice Settings
          </Typography>
          
          {/* Quick Presets */}
          <Grid container spacing={2} sx={{ mb: 3 }}>
            <Grid item xs={12}>
              <Typography variant="body2" sx={{ mb: 1, fontWeight: 500 }}>
                Quick Presets
              </Typography>
              <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                <Chip
                  label="Optimized (Edge TTS)"
                  color={config.voice.tts_engine === 'edge-tts' && config.stt.engine === 'google' ? 'primary' : 'default'}
                  onClick={() => {
                    updateConfig('voice.tts_engine', 'edge-tts');
                    updateConfig('stt.engine', 'google');
                    updateConfig('voice.tts_voice', 'en-US-AvaNeural');
                  }}
                  variant={config.voice.tts_engine === 'edge-tts' && config.stt.engine === 'google' ? 'filled' : 'outlined'}
                />
                <Chip
                  label="Fallback (Local)"
                  color={config.voice.tts_engine === 'pyttsx3' && config.stt.engine === 'sphinx' ? 'primary' : 'default'}
                  onClick={() => {
                    updateConfig('voice.tts_engine', 'pyttsx3');
                    updateConfig('stt.engine', 'sphinx');
                  }}
                  variant={config.voice.tts_engine === 'pyttsx3' && config.stt.engine === 'sphinx' ? 'filled' : 'outlined'}
                />
              </Box>
            </Grid>
          </Grid>
          
          <Divider sx={{ my: 2 }} />
          
          <Grid container spacing={3}>
            <Grid item xs={12}>
              <FormControl fullWidth>
                <InputLabel>TTS Engine</InputLabel>
                <Select
                  value={config.voice.tts_engine}
                  label="TTS Engine"
                  onChange={(e) => updateConfig('voice.tts_engine', e.target.value)}
                >
                  <MenuItem value="edge-tts">Edge TTS (Recommended)</MenuItem>
                  <MenuItem value="pyttsx3">PyTTSX3 (Local Fallback)</MenuItem>
                </Select>
              </FormControl>
            </Grid>

            <Grid item xs={12}>
              <FormControl fullWidth>
                <InputLabel>Voice</InputLabel>
                <Select
                  value={config.voice.tts_voice}
                  label="Voice"
                  onChange={(e) => updateConfig('voice.tts_voice', e.target.value)}
                >
                  <MenuItem value="en-US-AvaNeural">Ava (Female)</MenuItem>
                  <MenuItem value="en-US-AndrewNeural">Andrew (Male)</MenuItem>
                  <MenuItem value="en-US-EmmaNeural">Emma (Female)</MenuItem>
                  <MenuItem value="en-US-BrianNeural">Brian (Male)</MenuItem>
                  <MenuItem value="en-US-JennyNeural">Jenny (Female)</MenuItem>
                  <MenuItem value="en-US-GuyNeural">Guy (Male)</MenuItem>
                  <MenuItem value="en-US-AriaNeural">Aria (Female)</MenuItem>
                  <MenuItem value="en-US-DavisNeural">Davis (Male)</MenuItem>
                  <MenuItem value="en-US-JaneNeural">Jane (Female)</MenuItem>
                  <MenuItem value="en-US-JasonNeural">Jason (Male)</MenuItem>
                </Select>
              </FormControl>
            </Grid>

            <Grid item xs={12}>
              <Typography variant="body2" sx={{ mb: 1 }}>
                Speech Rate: {config.voice.tts_rate}x
              </Typography>
              <Slider
                value={config.voice.tts_rate}
                min={0.5}
                max={2.0}
                step={0.1}
                onChange={(e, value) => updateConfig('voice.tts_rate', value)}
                valueLabelDisplay="auto"
              />
            </Grid>

            <Grid item xs={12}>
              <Typography variant="body2" sx={{ mb: 1 }}>
                Volume: {Math.round(config.voice.tts_volume * 100)}%
              </Typography>
              <Slider
                value={config.voice.tts_volume}
                min={0}
                max={1}
                step={0.1}
                onChange={(e, value) => updateConfig('voice.tts_volume', value)}
                valueLabelDisplay="auto"
                valueLabelFormat={(value) => `${Math.round(value * 100)}%`}
              />
            </Grid>

            <Grid item xs={12}>
              <FormControlLabel
                control={
                  <Switch
                    checked={config.voice.use_sound_effects}
                    onChange={(e) => updateConfig('voice.use_sound_effects', e.target.checked)}
                  />
                }
                label="Enable Sound Effects"
              />
            </Grid>
          </Grid>
        </TabPanel>

        {/* Speech Recognition Settings */}
        <TabPanel value={tabValue} index={1}>
          <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
            Speech Recognition
          </Typography>
          
          <Grid container spacing={3}>
            <Grid item xs={12}>
              <FormControl fullWidth>
                <InputLabel>STT Engine</InputLabel>
                <Select
                  value={config.stt.engine}
                  label="STT Engine"
                  onChange={(e) => updateConfig('stt.engine', e.target.value)}
                >
                  <MenuItem value="google">Google Speech Recognition (Recommended)</MenuItem>
                  <MenuItem value="sphinx">CMU Sphinx (Offline)</MenuItem>
                  <MenuItem value="whisper">OpenAI Whisper (Local)</MenuItem>
                </Select>
              </FormControl>
            </Grid>

            <Grid item xs={12}>
              <Typography variant="body2" sx={{ mb: 1 }}>
                Timeout: {config.stt.timeout}s
              </Typography>
              <Slider
                value={config.stt.timeout}
                min={5}
                max={30}
                step={1}
                onChange={(e, value) => updateConfig('stt.timeout', value)}
                valueLabelDisplay="auto"
              />
            </Grid>

            <Grid item xs={12}>
              <Typography variant="body2" sx={{ mb: 1 }}>
                Energy Threshold: {config.stt.energy_threshold}
              </Typography>
              <Slider
                value={config.stt.energy_threshold}
                min={1000}
                max={5000}
                step={100}
                onChange={(e, value) => updateConfig('stt.energy_threshold', value)}
                valueLabelDisplay="auto"
              />
            </Grid>
          </Grid>
        </TabPanel>

        {/* AI Settings */}
        <TabPanel value={tabValue} index={2}>
          <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
            AI Configuration
          </Typography>
          
          <Grid container spacing={3}>
            <Grid item xs={12}>
              <FormControl fullWidth>
                <InputLabel>LLM Engine</InputLabel>
                <Select
                  value={config.llm.engine}
                  label="LLM Engine"
                  onChange={(e) => updateConfig('llm.engine', e.target.value)}
                >
                  <MenuItem value="tgpt">Terminal GPT</MenuItem>
                  <MenuItem value="openai">OpenAI GPT</MenuItem>
                  <MenuItem value="local">Local LLM</MenuItem>
                </Select>
              </FormControl>
            </Grid>

            <Grid item xs={12}>
              <TextField
                fullWidth
                multiline
                rows={6}
                label="System Prompt"
                value={config.llm.system_prompt}
                onChange={(e) => updateConfig('llm.system_prompt', e.target.value)}
                helperText="This defines how Aiden behaves and responds"
              />
            </Grid>
          </Grid>
        </TabPanel>

        {/* User Profile */}
        <TabPanel value={tabValue} index={3}>
          <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
            User Profile
          </Typography>
          
          <Grid container spacing={3}>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Your Name"
                value={userProfile.personal.name}
                onChange={(e) => updateUserProfile('personal.name', e.target.value)}
              />
            </Grid>

            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Preferred Address"
                value={userProfile.personal.form_of_address}
                onChange={(e) => updateUserProfile('personal.form_of_address', e.target.value)}
                helperText="How Aiden should address you (e.g., Boss, Sir, etc.)"
              />
            </Grid>

            <Grid item xs={12}>
              <FormControl fullWidth>
                <InputLabel>Response Style</InputLabel>
                <Select
                  value={userProfile.preferences.brevity}
                  label="Response Style"
                  onChange={(e) => updateUserProfile('preferences.brevity', e.target.value)}
                >
                  <MenuItem value="brief">Brief</MenuItem>
                  <MenuItem value="medium">Medium</MenuItem>
                  <MenuItem value="detailed">Detailed</MenuItem>
                </Select>
              </FormControl>
            </Grid>

            <Grid item xs={12}>
              <Paper sx={{ p: 2, background: '#2a2a2a' }}>
                <Typography variant="subtitle2" sx={{ mb: 1 }}>
                  Interaction Statistics
                </Typography>
                <Chip 
                  label={`Total: ${userProfile.history.interactions.length}`} 
                  sx={{ mr: 1, mb: 1 }}
                />
                <Chip 
                  label={`Last login: ${new Date(userProfile.personal.last_login).toLocaleDateString()}`} 
                  sx={{ mr: 1, mb: 1 }}
                />
              </Paper>
            </Grid>
          </Grid>
        </TabPanel>

        {/* Bottom Actions */}
        <Box sx={{ 
          p: 2, 
          borderTop: '1px solid #2a2a2a',
          mt: 'auto',
          display: 'flex',
          gap: 1,
          justifyContent: 'space-between'
        }}>
          <Button
            variant="outlined"
            onClick={resetToDefaults}
            startIcon={<Refresh />}
            sx={{ borderColor: '#f7c94c', color: '#f7c94c' }}
          >
            Reset to Defaults
          </Button>
          
          <Button
            variant="contained"
            onClick={saveConfig}
            disabled={!hasChanges || saving}
            startIcon={<Save />}
            sx={{
              background: hasChanges 
                ? 'linear-gradient(45deg, #4ade80, #22c55e)'
                : '#2a2a2a',
              '&:hover': {
                background: hasChanges 
                  ? 'linear-gradient(45deg, #22c55e, #16a34a)'
                  : '#3a3a3a',
              }
            }}
          >
            {saving ? 'Saving...' : 'Save Changes'}
          </Button>
        </Box>
      </motion.div>
    </Drawer>
  );
};

export default ConfigPanel; 