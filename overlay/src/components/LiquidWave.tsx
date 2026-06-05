import React from 'react';
import { motion, type Variants } from 'framer-motion';

interface LiquidWaveProps {
    state: 'listening' | 'thinking' | 'replying';
    displayText?: string;
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

const LiquidWave: React.FC<LiquidWaveProps> = ({ state, displayText }) => {
    const gradientId = 'aidenGradient';
    const config = waveConfig[state];
    const viewBoxWidth = 1200;

    // Determine what text to show
    const getDisplayText = () => {
        if (displayText) return displayText;

        // Fallback to state labels
        switch (state) {
            case 'listening':
                return 'Listening...';
            case 'thinking':
                return 'Thinking...';
            case 'replying':
                return 'Here is the answer...';
            default:
                return '';
        }
    };

    const textToDisplay = getDisplayText();
    const isLongText = textToDisplay.length > 95;
    const isExtraLongText = textToDisplay.length > 150;

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
                top: 20,
                width: '100%',
                maxWidth: 'calc(100vw - 48px)',
                textAlign: 'center',
                pointerEvents: 'none',
                display: 'flex',
                flexDirection: 'row',
                alignItems: 'flex-start',
                justifyContent: 'center',
                gap: '10px',
                minWidth: 0
            }}>
                {/* State Indicator Dot - Only for listening */}
                {state === 'listening' && (
                    <motion.div
                        initial={{ scale: 0, opacity: 0 }}
                        animate={{
                            scale: 1,
                            opacity: 1
                        }}
                        exit={{ scale: 0, opacity: 0 }}
                        transition={{ duration: 0.3, ease: "easeOut" }}
                        style={{
                            width: '8px',
                            height: '8px',
                            minWidth: '8px',
                            marginTop: '7px',
                            borderRadius: '50%',
                            backgroundColor: '#60a5fa',
                            boxShadow: '0 0 10px rgba(96, 165, 250, 0.8)'
                        }}
                    />
                )}

                {/* Animated Text with Aiden Dashboard Shimmer */}
                <motion.div
                    key={state}
                    initial={{ opacity: 0, y: -10, scale: 0.9 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: 10, scale: 0.9 }}
                    transition={{ duration: 0.4, ease: "easeOut" }}
                    style={{
                        position: 'relative',
                        overflow: 'visible',
                        minWidth: 0,
                        maxWidth: 'min(1120px, calc(100vw - 78px))'
                    }}
                >
                    {/* Background Glow */}
                    <div style={{
                        position: 'absolute',
                        top: '50%',
                        left: '50%',
                        transform: 'translate(-50%, -50%)',
                        width: '90%',
                        height: '70%',
                        background: 'radial-gradient(ellipse at center, rgba(76, 130, 247, 0.35) 0%, rgba(135, 206, 250, 0.25) 20%, rgba(59, 130, 246, 0.18) 40%, rgba(76, 130, 247, 0.1) 60%, transparent 80%)',
                        filter: 'blur(30px)',
                        zIndex: 0,
                        opacity: 0.7,
                        pointerEvents: 'none',
                        animation: 'pulse-glow 3s ease-in-out infinite'
                    }} />

                    <div style={{
                        position: 'relative',
                        zIndex: 10,
                        maxWidth: '100%',
                        display: '-webkit-box',
                        WebkitBoxOrient: 'vertical',
                        WebkitLineClamp: 2,
                        overflow: 'hidden',
                        fontFamily: 'Inter, sans-serif',
                        fontWeight: 700,
                        fontSize: isExtraLongText ? '12px' : isLongText ? '13px' : '15px',
                        lineHeight: isExtraLongText ? 1.18 : isLongText ? 1.22 : 1.28,
                        letterSpacing: '0.5px',
                        whiteSpace: 'normal',
                        overflowWrap: 'anywhere',
                        wordBreak: 'normal',
                        hyphens: 'auto',
                        background: 'linear-gradient(90deg, rgba(255, 255, 255, 0.6) 0%, rgba(255, 255, 255, 1) 15%, rgba(135, 206, 250, 1) 30%, rgba(76, 130, 247, 1) 45%, rgba(59, 130, 246, 1) 50%, rgba(76, 130, 247, 1) 55%, rgba(135, 206, 250, 1) 70%, rgba(255, 255, 255, 1) 85%, rgba(255, 255, 255, 0.6) 100%)',
                        backgroundSize: '200% 100%',
                        backgroundClip: 'text',
                        WebkitBackgroundClip: 'text',
                        WebkitTextFillColor: 'transparent',
                        animation: 'shimmer 2.5s ease-in-out infinite',
                        filter: 'drop-shadow(0 0 5px rgba(76, 130, 247, 0.4))'
                    }}>
                        {textToDisplay}
                    </div>
                </motion.div>
            </div>

            {/* Shimmer and Pulse Keyframes */}
            <style>{`
                @keyframes shimmer {
                    0% {
                        background-position: -200% 0;
                    }
                    100% {
                        background-position: 200% 0;
                    }
                }

                @keyframes pulse-glow {
                    0%, 100% {
                        opacity: 0.65;
                        filter: blur(30px);
                    }
                    50% {
                        opacity: 0.8;
                        filter: blur(32px);
                    }
                }
            `}</style>
        </motion.div>
    );
};

export default LiquidWave;
