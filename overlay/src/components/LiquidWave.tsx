import React from 'react';
import { motion, type Variants } from 'framer-motion';

interface LiquidWaveProps {
    state: 'listening' | 'thinking' | 'replying';
}

// Configuration for each state
const waveConfig = {
    listening: {
        width: 1200,
        height: 200,
        amplitude: 80,
        speed: 5
    },
    thinking: {
        width: 800,
        height: 200,
        amplitude: 50,
        speed: 2.5
    },
    replying: {
        width: 1200,
        height: 200,
        amplitude: 70,
        speed: 10
    }
};

const LiquidWave: React.FC<LiquidWaveProps> = ({ state }) => {
    // Aiden Blue palette
    const gradientId = 'aidenGradient';
    const config = waveConfig[state];

    // We use a fixed viewBox width to define the paths
    const viewBoxWidth = 1200;

    // Listening: Gentle, organic ripple - CENTERED
    const listeningPath = [
        `M0,0 C${viewBoxWidth * 0.25},${config.amplitude * 0.3} ${viewBoxWidth * 0.4},${config.amplitude} ${viewBoxWidth * 0.5},${config.amplitude} C${viewBoxWidth * 0.6},${config.amplitude} ${viewBoxWidth * 0.75},${config.amplitude * 0.3} ${viewBoxWidth},0 Z`,
        `M0,0 C${viewBoxWidth * 0.25},${config.amplitude * 0.4} ${viewBoxWidth * 0.4},${config.amplitude + 10} ${viewBoxWidth * 0.5},${config.amplitude + 10} C${viewBoxWidth * 0.6},${config.amplitude + 10} ${viewBoxWidth * 0.75},${config.amplitude * 0.4} ${viewBoxWidth},0 Z`,
        `M0,0 C${viewBoxWidth * 0.25},${config.amplitude * 0.3} ${viewBoxWidth * 0.4},${config.amplitude} ${viewBoxWidth * 0.5},${config.amplitude} C${viewBoxWidth * 0.6},${config.amplitude} ${viewBoxWidth * 0.75},${config.amplitude * 0.3} ${viewBoxWidth},0 Z`
    ];

    // Thinking: Smooth, deep breathing - CENTERED
    const thinkingPath = [
        `M0,0 C${viewBoxWidth * 0.25},${config.amplitude * 0.6} ${viewBoxWidth * 0.4},${config.amplitude * 1.2} ${viewBoxWidth * 0.5},${config.amplitude * 1.2} C${viewBoxWidth * 0.6},${config.amplitude * 1.2} ${viewBoxWidth * 0.75},${config.amplitude * 0.6} ${viewBoxWidth},0 Z`,
        `M0,0 C${viewBoxWidth * 0.25},${config.amplitude * 0.8} ${viewBoxWidth * 0.4},${config.amplitude * 1.4} ${viewBoxWidth * 0.5},${config.amplitude * 1.4} C${viewBoxWidth * 0.6},${config.amplitude * 1.4} ${viewBoxWidth * 0.75},${config.amplitude * 0.8} ${viewBoxWidth},0 Z`,
        `M0,0 C${viewBoxWidth * 0.25},${config.amplitude * 0.6} ${viewBoxWidth * 0.4},${config.amplitude * 1.2} ${viewBoxWidth * 0.5},${config.amplitude * 1.2} C${viewBoxWidth * 0.6},${config.amplitude * 1.2} ${viewBoxWidth * 0.75},${config.amplitude * 0.6} ${viewBoxWidth},0 Z`
    ];

    // Replying: Natural, flowing wave - CENTERED
    const replyingPath = [
        `M0,0 C${viewBoxWidth * 0.25},${config.amplitude * 0.2} ${viewBoxWidth * 0.4},${config.amplitude} ${viewBoxWidth * 0.5},${config.amplitude} C${viewBoxWidth * 0.6},${config.amplitude} ${viewBoxWidth * 0.75},${config.amplitude * 0.2} ${viewBoxWidth},0 Z`,
        `M0,0 C${viewBoxWidth * 0.25},${config.amplitude * 0.6} ${viewBoxWidth * 0.4},${config.amplitude + 20} ${viewBoxWidth * 0.5},${config.amplitude + 20} C${viewBoxWidth * 0.6},${config.amplitude + 20} ${viewBoxWidth * 0.75},${config.amplitude * 0.6} ${viewBoxWidth},0 Z`,
        `M0,0 C${viewBoxWidth * 0.25},${config.amplitude * 0.2} ${viewBoxWidth * 0.4},${config.amplitude} ${viewBoxWidth * 0.5},${config.amplitude} C${viewBoxWidth * 0.6},${config.amplitude} ${viewBoxWidth * 0.75},${config.amplitude * 0.2} ${viewBoxWidth},0 Z`
    ];

    const currentVariants: Variants = {
        listening: {
            d: listeningPath,
            transition: { duration: config.speed, repeat: Infinity, ease: "easeInOut" }
        },
        thinking: {
            d: thinkingPath,
            transition: { duration: config.speed, repeat: Infinity, ease: "easeInOut" }
        },
        replying: {
            d: replyingPath,
            transition: { duration: config.speed, repeat: Infinity, ease: "easeInOut" }
        }
    };

    return (
        <motion.div
            animate={{ width: config.width, height: config.height }}
            transition={{ duration: 0.5, ease: "easeInOut" }}
            style={{
                display: 'flex',
                justifyContent: 'center',
                filter: 'drop-shadow(0px 4px 20px rgba(76, 130, 247, 0.5))'
            }}
        >
            <svg
                width="100%"
                height="100%"
                viewBox={`0 0 ${viewBoxWidth} ${config.height}`}
                preserveAspectRatio="none"
                style={{ overflow: 'visible' }}
            >
                <defs>
                    <linearGradient id={gradientId} x1="0%" y1="0%" x2="0%" y2="100%">
                        <stop offset="0%" stopColor="#042a70ff" stopOpacity="1" />
                        <stop offset="50%" stopColor="#0d2b6dff" stopOpacity="0.9" />
                        <stop offset="100%" stopColor="#0f3781ff" stopOpacity="1" />
                    </linearGradient>
                </defs>

                <motion.path
                    fill={`url(#${gradientId})`}
                    animate={state}
                    variants={currentVariants}
                    initial="listening"
                />

                <motion.path
                    fill={`url(#${gradientId})`}
                    fillOpacity="0.4"
                    animate={state}
                    variants={{
                        listening: {
                            d: listeningPath,
                            transition: { duration: config.speed, repeat: Infinity, ease: "easeInOut", delay: 1.5 }
                        },
                        thinking: {
                            d: thinkingPath,
                            transition: { duration: config.speed, repeat: Infinity, ease: "easeInOut", delay: 0.5 }
                        },
                        replying: {
                            d: replyingPath,
                            transition: { duration: config.speed, repeat: Infinity, ease: "easeInOut", delay: 1.5 }
                        }
                    }}
                    style={{ mixBlendMode: 'screen' }}
                />
            </svg>

            <div style={{
                position: 'absolute',
                top: 25,
                width: '100%',
                textAlign: 'center',
                color: 'white',
                fontFamily: 'Inter, sans-serif',
                fontWeight: 500,
                fontSize: '15px',
                letterSpacing: '0.5px',
                textShadow: '0 1px 3px rgba(0,0,0,0.3)',
                pointerEvents: 'none'
            }}>
                {state === 'listening' && "Listening..."}
                {state === 'thinking' && "Thinking..."}
                {state === 'replying' && "Here is the answer..."}
            </div>
        </motion.div>
    );
};

export default LiquidWave;
