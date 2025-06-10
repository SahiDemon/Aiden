import React from 'react';
import {
  Card,
  CardContent,
  Typography,
  Box,
  Chip,
  IconButton,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Divider,
  Button,
  Grid
} from '@mui/material';
import {
  Check,
  Error,
  Info,
  Launch,
  Folder,
  Code,
  Web,
  PlayArrow,
  Settings,
  Description,
  Image,
  MusicNote,
  Movie,
  Games
} from '@mui/icons-material';
import { motion, AnimatePresence } from 'framer-motion';

const ActionCard = ({ action, onItemClick }) => {
  // Add validation for action prop
  if (!action || typeof action !== 'object') {
    console.error('ActionCard: Invalid action prop:', action);
    return (
      <Box sx={{ 
        p: 2, 
        backgroundColor: '#1a1a1a', 
        border: '1px solid #f87171',
        borderRadius: 2,
        color: '#f87171'
      }}>
        <Typography variant="body2">
          Error: Invalid action data
        </Typography>
      </Box>
    );
  }

  // Ensure required properties exist
  const safeAction = {
    type: action.type || 'unknown',
    title: action.title || 'Unknown Action',
    message: action.message || '',
    subtitle: action.subtitle || '',
    status: action.status || 'Active',
    items: action.items || [],
    buttons: action.buttons || []
  };

  const getActionIcon = (actionType) => {
    switch (actionType) {
      case 'app_list':
        return <Launch sx={{ color: '#4c82f7' }} />;
      case 'project_list':
        return <Folder sx={{ color: '#f59e0b' }} />;
      case 'action_success':
        return <Check sx={{ color: '#4ade80' }} />;
      case 'action_error':
        return <Error sx={{ color: '#f87171' }} />;
      case 'url_opened':
        return <Web sx={{ color: '#06b6d4' }} />;
      case 'project_created':
        return <Code sx={{ color: '#8b5cf6' }} />;
      default:
        return <Info sx={{ color: '#9ca3af' }} />;
    }
  };

  const getItemIcon = (item) => {
    if (!item) return <Launch />;
    
    const name = item.name ? item.name.toLowerCase() : (typeof item === 'string' ? item.toLowerCase() : '');
    
    // App icons
    if (name.includes('chrome') || name.includes('browser')) return <Web />;
    if (name.includes('code') || name.includes('vscode')) return <Code />;
    if (name.includes('notepad') || name.includes('text')) return <Description />;
    if (name.includes('paint') || name.includes('photo')) return <Image />;
    if (name.includes('media') || name.includes('music')) return <MusicNote />;
    if (name.includes('video') || name.includes('movie')) return <Movie />;
    if (name.includes('game')) return <Games />;
    if (name.includes('setting') || name.includes('control')) return <Settings />;
    
    // Default icons
    if (safeAction.type === 'project_list') return <Folder />;
    return <Launch />;
  };

  const getActionColor = (actionType) => {
    switch (actionType) {
      case 'app_list':
        return '#4c82f7';
      case 'project_list':
        return '#f59e0b';
      case 'action_success':
        return '#4ade80';
      case 'action_error':
        return '#f87171';
      case 'url_opened':
        return '#06b6d4';
      case 'project_created':
        return '#8b5cf6';
      default:
        return '#9ca3af';
    }
  };

  const handleItemClick = (item) => {
    if (onItemClick && item) {
      onItemClick(item, safeAction.type);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
    >
      <Card sx={{
        backgroundColor: '#1a1a1a',
        border: '1px solid #333',
        borderRadius: '16px',
        mb: 2,
        overflow: 'hidden',
        position: 'relative'
      }}>
        {/* Header */}
        <Box sx={{
          background: `linear-gradient(135deg, ${getActionColor(safeAction.type)}20, ${getActionColor(safeAction.type)}10)`,
          borderBottom: `1px solid ${getActionColor(safeAction.type)}30`,
          p: 2
        }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
            <Box sx={{
              backgroundColor: `${getActionColor(safeAction.type)}20`,
              borderRadius: '12px',
              p: 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}>
              {getActionIcon(safeAction.type)}
            </Box>
            <Box sx={{ flex: 1 }}>
              <Typography variant="h6" sx={{ 
                color: '#fff',
                fontSize: '1rem',
                fontWeight: 600,
                mb: 0.5
              }}>
                {safeAction.title}
              </Typography>
              {safeAction.subtitle && (
                <Typography variant="body2" sx={{ 
                  color: '#9ca3af',
                  fontSize: '0.875rem'
                }}>
                  {safeAction.subtitle}
                </Typography>
              )}
            </Box>
            <Chip
              size="small"
              label={safeAction.status}
              sx={{
                backgroundColor: `${getActionColor(safeAction.type)}30`,
                color: getActionColor(safeAction.type),
                fontSize: '0.75rem',
                fontWeight: 600
              }}
            />
          </Box>
        </Box>

        <CardContent sx={{ p: 0 }}>
          {/* Message */}
          {safeAction.message && (
            <Box sx={{ p: 2, pb: safeAction.items.length > 0 ? 1 : 2 }}>
              <Typography variant="body2" sx={{ 
                color: '#e5e7eb',
                lineHeight: 1.6
              }}>
                {safeAction.message}
              </Typography>
            </Box>
          )}

          {/* Items List */}
          {safeAction.items.length > 0 && (
            <Box>
              {safeAction.message && <Divider sx={{ borderColor: '#333' }} />}
              <List sx={{ py: 1 }}>
                <AnimatePresence>
                  {safeAction.items.map((item, index) => (
                    <motion.div
                      key={index}
                      initial={{ opacity: 0, x: -20 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: index * 0.05, duration: 0.3 }}
                    >
                      <ListItem
                        button
                        onClick={() => handleItemClick(item)}
                        sx={{
                          py: 1,
                          px: 2,
                          '&:hover': {
                            backgroundColor: `${getActionColor(safeAction.type)}10`,
                            transform: 'translateX(4px)'
                          },
                          transition: 'all 0.2s ease',
                          borderRadius: '8px',
                          mx: 1
                        }}
                      >
                        <ListItemIcon sx={{ minWidth: 40 }}>
                          <Box sx={{
                            color: getActionColor(safeAction.type),
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center'
                          }}>
                            {getItemIcon(item)}
                          </Box>
                        </ListItemIcon>
                        <ListItemText
                          primary={
                            <Typography variant="body2" sx={{ 
                              color: '#fff',
                              fontWeight: 500
                            }}>
                              {typeof item === 'object' ? (item.name || 'Unknown Item') : String(item)}
                            </Typography>
                          }
                          secondary={typeof item === 'object' && item.path && (
                            <Typography variant="caption" sx={{ 
                              color: '#9ca3af',
                              fontSize: '0.75rem'
                            }}>
                              {item.path}
                            </Typography>
                          )}
                        />
                        <PlayArrow sx={{ 
                          color: '#9ca3af',
                          fontSize: 16,
                          opacity: 0.7
                        }} />
                      </ListItem>
                    </motion.div>
                  ))}
                </AnimatePresence>
              </List>
            </Box>
          )}

          {/* Action Buttons */}
          {safeAction.buttons.length > 0 && (
            <Box sx={{ p: 2, pt: 1 }}>
              <Grid container spacing={1}>
                {safeAction.buttons.map((button, index) => (
                  <Grid item xs={6} key={index}>
                    <Button
                      fullWidth
                      variant="outlined"
                      size="small"
                      onClick={() => handleItemClick(button)}
                      sx={{
                        borderColor: getActionColor(safeAction.type),
                        color: getActionColor(safeAction.type),
                        '&:hover': {
                          borderColor: getActionColor(safeAction.type),
                          backgroundColor: `${getActionColor(safeAction.type)}10`
                        }
                      }}
                    >
                      {typeof button === 'object' ? (button.label || button.name || 'Button') : String(button)}
                    </Button>
                  </Grid>
                ))}
              </Grid>
            </Box>
          )}
        </CardContent>

        {/* Animated border */}
        <Box sx={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          height: '2px',
          background: `linear-gradient(90deg, ${getActionColor(safeAction.type)}, transparent)`,
          opacity: 0.8
        }} />
      </Card>
    </motion.div>
  );
};

export default ActionCard; 