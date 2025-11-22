import { useState, useEffect, useRef, useCallback } from 'react';

type VoiceActivityStatus = 'listening' | 'processing' | 'idle' | 'speaking';
type OverlayState = 'listening' | 'thinking' | 'replying' | 'idle';

interface VoiceActivity {
    status: VoiceActivityStatus;
    speaking: boolean;
}

interface Message {
    role: 'user' | 'assistant';
    content: string;
    timestamp: string;
}

interface UseWebSocketReturn {
    connected: boolean;
    overlayState: OverlayState;
    currentText: string;
    userInput: string;
}

export const useWebSocket = (url = 'ws://localhost:5000/api/v1/ws'): UseWebSocketReturn => {
    const [connected, setConnected] = useState(false);
    const [overlayState, setOverlayState] = useState<OverlayState>('idle');
    const [currentText, setCurrentText] = useState('');
    const [userInput, setUserInput] = useState('');

    const wsRef = useRef<WebSocket | null>(null);
    const reconnectTimeoutRef = useRef<number | null>(null);
    const reconnectAttemptsRef = useRef(0);
    const isConnectingRef = useRef(false);
    const shouldReconnectRef = useRef(true);

    const connect = useCallback(() => {
        if (!shouldReconnectRef.current) {
            console.log('[Overlay WebSocket] Component unmounted, skipping connection');
            return;
        }

        if (isConnectingRef.current) {
            console.log('[Overlay WebSocket] Already connecting, skipping...');
            return;
        }

        if (wsRef.current?.readyState === WebSocket.OPEN) {
            console.log('[Overlay WebSocket] Already connected, skipping...');
            return;
        }

        if (wsRef.current) {
            try {
                console.log('[Overlay WebSocket] Closing existing connection');
                wsRef.current.onclose = null;
                wsRef.current.close();
            } catch (e) {
                console.error('[Overlay WebSocket] Error closing existing connection:', e);
            }
            wsRef.current = null;
        }

        isConnectingRef.current = true;

        try {
            const ws = new WebSocket(url);

            ws.onopen = () => {
                console.log('[Overlay WebSocket] Connected to Aiden API');
                setConnected(true);
                reconnectAttemptsRef.current = 0;
                isConnectingRef.current = false;
            };

            ws.onclose = () => {
                console.log('[Overlay WebSocket] Disconnected');
                setConnected(false);
                isConnectingRef.current = false;
                setOverlayState('idle');
                setCurrentText('');
                setUserInput('');

                if (!shouldReconnectRef.current) {
                    console.log('[Overlay WebSocket] Component unmounted, not reconnecting');
                    return;
                }

                const delay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 30000);
                reconnectAttemptsRef.current += 1;

                reconnectTimeoutRef.current = window.setTimeout(() => {
                    console.log(`[Overlay WebSocket] Reconnecting... (attempt ${reconnectAttemptsRef.current})`);
                    connect();
                }, delay);
            };

            ws.onerror = (error) => {
                console.error('[Overlay WebSocket] Error:', error);
                isConnectingRef.current = false;
            };

            ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);

                    switch (data.type) {
                        case 'message': {
                            const message: Message = data.data;

                            if (message.role === 'user') {
                                setUserInput(message.content);
                                setCurrentText('');
                            } else if (message.role === 'assistant') {
                                setCurrentText(message.content);
                            }
                            break;
                        }

                        case 'voice_activity': {
                            const voiceActivity: VoiceActivity = data.data;

                            if (voiceActivity.status === 'listening') {
                                setOverlayState('listening');
                                setUserInput('');
                                setCurrentText('');
                            } else if (voiceActivity.status === 'processing') {
                                setOverlayState('thinking');
                            } else if (voiceActivity.speaking) {
                                setOverlayState('replying');
                            } else {
                                setOverlayState('idle');
                            }
                            break;
                        }

                        case 'assistant_speaking': {
                            const speakingText = data.data?.text || '';
                            setCurrentText(speakingText);
                            setOverlayState('replying');
                            break;
                        }

                        case 'ping':
                            if (ws.readyState === WebSocket.OPEN) {
                                ws.send(JSON.stringify({ type: 'pong' }));
                            }
                            break;

                        case 'timer_update':
                        case 'system_metric':
                        case 'device_update':
                        case 'esp32_update':
                            // Ignore these messages in overlay (only relevant for dashboard)
                            break;

                        default:
                            console.log('[Overlay WebSocket] Unknown message type:', data.type, data);
                            break;
                    }
                } catch (error) {
                    console.error('[Overlay WebSocket] Error parsing message:', error);
                }
            };

            wsRef.current = ws;
        } catch (error) {
            console.error('[Overlay WebSocket] Error creating WebSocket:', error);
            isConnectingRef.current = false;
        }
    }, [url]);

    useEffect(() => {
        console.log('[Overlay WebSocket] Initializing connection...');
        shouldReconnectRef.current = true;
        connect();

        const heartbeat = setInterval(() => {
            if (wsRef.current?.readyState === WebSocket.OPEN) {
                wsRef.current.send(JSON.stringify({ type: 'ping' }));
            }
        }, 30000);

        return () => {
            console.log('[Overlay WebSocket] Cleanup: closing connection');
            shouldReconnectRef.current = false;
            clearInterval(heartbeat);
            if (reconnectTimeoutRef.current) {
                clearTimeout(reconnectTimeoutRef.current);
                reconnectTimeoutRef.current = null;
            }
            isConnectingRef.current = false;
            if (wsRef.current) {
                wsRef.current.onclose = null;
                wsRef.current.onerror = null;
                wsRef.current.close();
                wsRef.current = null;
            }
        };
    }, [connect]);

    return {
        connected,
        overlayState,
        currentText,
        userInput,
    };
};

export default useWebSocket;
