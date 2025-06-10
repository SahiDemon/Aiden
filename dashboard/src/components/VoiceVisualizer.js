import React from 'react';
import { Box } from '@mui/material';
import { motion } from 'framer-motion';

const VoiceVisualizer = ({ active = false }) => {
  const bars = Array.from({ length: 7 }, (_, i) => i);
  
  const barVariants = {
    inactive: {
      height: 4,
      opacity: 0.3
    },
    active: {
      height: [4, 25, 40, 25, 4],
      opacity: 1,
      transition: {
        duration: 1.5,
        repeat: Infinity,
        ease: "easeInOut",
        delay: 0.1 * Math.random()
      }
    }
  };

  return (
    <Box sx={{ 
      display: 'flex', 
      alignItems: 'center', 
      justifyContent: 'center',
      gap: 0.5,
      height: 40,
      mx: 2
    }}>
      {bars.map((index) => (
        <motion.div
          key={index}
          variants={barVariants}
          animate={active ? 'active' : 'inactive'}
          style={{
            width: 4,
            backgroundColor: active ? '#4c82f7' : '#666',
            borderRadius: 2,
            transformOrigin: 'bottom'
          }}
        />
      ))}
    </Box>
  );
};

export default VoiceVisualizer; 