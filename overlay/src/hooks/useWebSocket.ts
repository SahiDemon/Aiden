import { useState, useEffect, useRef, useCallback } from 'react';

type VoiceActivityStatus = 'listening' | 'processing' | 'idle' | 'speaking';
type OverlayState = 'listening' | 'thinking' | 'replying' | 'idle';
type IpcRendererBridge = {
    send?: (channel: string, ...args: unknown[]) => void;
};
type OverlayWindow = Window & typeof globalThis & {
    ipcRenderer?: IpcRendererBridge;
};

const raiseOverlay = () => {
    try {
        (window as OverlayWindow).ipcRenderer?.send?.('overlay:raise');
    } catch {
        // Non-Electron preview builds do not expose ipcRenderer.
    }
};

const hideOverlay = () => {
    try {
        (window as OverlayWindow).ipcRenderer?.send?.('overlay:hide');
    } catch {
        // Non-Electron preview builds do not expose ipcRenderer.
    }
};

interface VoiceActivity {
    status: VoiceActivityStatus;
    speaking: boolean;
    active?: boolean;
    source?: string;
}

interface Message {
    role: 'user' | 'assistant';
    content: string;
    timestamp: string;
    source?: string;
}

export interface SpeechWord { text: string; start: number; end: number }

interface UseWebSocketReturn {
    words: SpeechWord[];
    activeWord: number;
    connected: boolean;
    overlayState: OverlayState;
    currentText: string;
    userInput: string;
    sessionActive: boolean;
}

export const useWebSocket = (url = 'ws://localhost:5000/api/v1/ws'): UseWebSocketReturn => {
    const [words, setWords] = useState<SpeechWord[]>([]);
    const [activeWord, setActiveWord] = useState(-1);
    const speechIdRef = useRef('');
    const wordsRef = useRef<SpeechWord[]>([]);
    const [connected, setConnected] = useState(false);
    const [overlayState, setOverlayState] = useState<OverlayState>('idle');
    const [currentText, setCurrentText] = useState('');
    const [userInput, setUserInput] = useState('');
    const [sessionActive, setSessionActive] = useState(false);

    const wsRef = useRef<WebSocket | null>(null);
    const reconnectTimeoutRef = useRef<number | null>(null);
    const reconnectAttemptsRef = useRef(0);
    const isConnectingRef = useRef(false);
    const shouldReconnectRef = useRef(true);
    const sessionActiveRef = useRef(false);
    const overlayStateRef = useRef<OverlayState>('idle');
    const hideOverlayTimeoutRef = useRef<number | null>(null);
    const connectRef = useRef<(() => void) | null>(null);

    const clearHideOverlayTimeout = useCallback(() => {
        if (hideOverlayTimeoutRef.current !== null) {
            window.clearTimeout(hideOverlayTimeoutRef.current);
            hideOverlayTimeoutRef.current = null;
        }
    }, []);

    const raiseActiveOverlay = useCallback(() => {
        clearHideOverlayTimeout();
        raiseOverlay();
    }, [clearHideOverlayTimeout]);

    const scheduleOverlayHide = useCallback(() => {
        clearHideOverlayTimeout();
        hideOverlayTimeoutRef.current = window.setTimeout(() => {
            hideOverlay();
            hideOverlayTimeoutRef.current = null;
        }, 700);
    }, [clearHideOverlayTimeout]);

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
                overlayStateRef.current = 'idle';
                setCurrentText('');
                setUserInput('');
                setWords([]);
                setActiveWord(-1);
                speechIdRef.current = '';
                setSessionActive(false);
                sessionActiveRef.current = false;
                scheduleOverlayHide();

                if (!shouldReconnectRef.current) {
                    console.log('[Overlay WebSocket] Component unmounted, not reconnecting');
                    return;
                }

                const delay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 30000);
                reconnectAttemptsRef.current += 1;

                reconnectTimeoutRef.current = window.setTimeout(() => {
                    console.log(`[Overlay WebSocket] Reconnecting... (attempt ${reconnectAttemptsRef.current})`);
                    connectRef.current?.();
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
                        case 'voice_transcript': {
                            if (data.data?.source !== 'web_text' && overlayStateRef.current === 'listening') {
                                setUserInput(typeof data.data?.text === 'string' ? data.data.text : '');
                            }
                            break;
                        }
                        case 'tts_progress': {
                            const payload = data.data;
                            if (!payload?.speech_id || payload.speech_id !== speechIdRef.current) break;
                            if (payload.state === 'ended' || payload.state === 'blocked') {
                                setOverlayState('idle');
                                overlayStateRef.current = 'idle';
                                setSessionActive(false);
                                sessionActiveRef.current = false;
                                setActiveWord(-1);
                                if (payload.state === 'ended') speechIdRef.current = '';
                                scheduleOverlayHide();
                                break;
                            }
                            if (payload.source === 'web') {
                                raiseActiveOverlay();
                                setOverlayState('replying');
                                overlayStateRef.current = 'replying';
                                setSessionActive(true);
                                sessionActiveRef.current = true;
                            }
                            const position = payload.position;
                            if (typeof position === 'number' && Number.isFinite(position)) {
                                const timings = wordsRef.current;
                                setActiveWord(timings.reduce((latest, word, index) => position >= word.start ? index : latest, -1));
                            }
                            break;
                        }
                        case 'message': {
                            const message: Message = data.data;
                            if (message.source === 'web_text') break;

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
                            if (voiceActivity.source === 'web_text') break;
                            const previous = overlayStateRef.current;
                            const changeStage = (stage: OverlayState) => {
                                overlayStateRef.current = stage;
                                setOverlayState(stage);
                                const active = stage !== 'idle';
                                sessionActiveRef.current = active;
                                setSessionActive(active);
                                if (active) raiseActiveOverlay();
                                else {
                                    setUserInput('');
                                    setCurrentText('');
                                    setActiveWord(-1);
                                    scheduleOverlayHide();
                                }
                            };
                            // Explicit cancellation always wins, including inconsistent payloads.
                            if (voiceActivity.active === false) {
                                speechIdRef.current = '';
                                changeStage('idle');
                            } else if (voiceActivity.status === 'listening') {
                                changeStage('listening');
                                setUserInput('');
                                setCurrentText('');
                                setWords([]);
                                setActiveWord(-1);
                                speechIdRef.current = '';
                            } else if (voiceActivity.status === 'processing') {
                                changeStage('thinking');
                            } else if (voiceActivity.speaking || voiceActivity.status === 'speaking') {
                                changeStage('replying');
                            } else if (voiceActivity.status === 'idle') {
                                // STT sends idle when capture ends, before the AI starts.
                                // TTS sends idle when playback ends. Keep that distinction.
                                if (voiceActivity.active === true || (previous === 'listening' && sessionActiveRef.current)) {
                                    changeStage('thinking');
                                } else {
                                    changeStage('idle');
                                }
                            }
                            break;
                        }

                        case 'assistant_speaking': {
                            if (data.data?.source === 'web_text') break;
                            const speakingText = data.data?.text || '';
                            speechIdRef.current = data.data?.speech_id || '';
                            wordsRef.current = Array.isArray(data.data?.words) ? data.data.words : [];
                            setWords(wordsRef.current);
                            setActiveWord(-1);
                            raiseActiveOverlay();
                            setCurrentText(speakingText);
                            setOverlayState(data.data?.source === 'web' ? 'thinking' : 'replying');
                            overlayStateRef.current = data.data?.source === 'web' ? 'thinking' : 'replying';
                            setSessionActive(true);
                            sessionActiveRef.current = true;
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
    }, [raiseActiveOverlay, scheduleOverlayHide, url]);

    useEffect(() => {
        connectRef.current = connect;
    }, [connect]);

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
            clearHideOverlayTimeout();
            hideOverlay();
            isConnectingRef.current = false;
            if (wsRef.current) {
                wsRef.current.onclose = null;
                wsRef.current.onerror = null;
                wsRef.current.onmessage = null;
                wsRef.current.onopen = null;
                wsRef.current.close();
                wsRef.current = null;
            }
        };
    }, [clearHideOverlayTimeout, connect]);

    return {
        words,
        activeWord,
        connected,
        overlayState,
        currentText,
        userInput,
        sessionActive,
    };
};

export default useWebSocket;
