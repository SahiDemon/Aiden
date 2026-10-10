import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { useWebSocket } from './hooks/useWebSocket';
import LiquidWave from './components/LiquidWave';
import './App.css';
import type { SpeechWord } from './hooks/useWebSocket';

export type WaveState = 'listening' | 'thinking' | 'replying';
export function OverlaySurface({ active, state, text, connected = true, words = [], activeWord = -1 }: { active: boolean; state: WaveState; text: string; connected?: boolean; words?: SpeechWord[]; activeWord?: number }) {
  const reducedMotion = useReducedMotion();
  return <div className="app-container">
    <AnimatePresence>
      {active && <motion.div className={`assistant-presence state-${state}`} key="presence"
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        transition={{ duration: reducedMotion ? 0 : .35 }}>
        <div className="screen-aura" aria-hidden="true">
          <div className="aura-rim" />
          <div className="aura-edge edge-top" /><div className="aura-edge edge-bottom" />
          <div className="aura-edge edge-left" /><div className="aura-edge edge-right" />
          <div className="aura-corner corner-tl" /><div className="aura-corner corner-tr" />
          <div className="aura-corner corner-bl" /><div className="aura-corner corner-br" />
        </div>
        <motion.div className="capsule-position" initial={{ y: reducedMotion ? 0 : -12 }} animate={{ y: 0 }} exit={{ y: reducedMotion ? 0 : -8 }}>
          <LiquidWave state={state} displayText={text} words={words} activeWord={activeWord} />
        </motion.div>
      </motion.div>}
    </AnimatePresence>
    {!connected && <div className="connection-status"><i />Reconnecting to Aiden</div>}
  </div>;
}

export default function App() {
  const { connected, overlayState, currentText, userInput, sessionActive, words, activeWord } = useWebSocket();
  const state: WaveState = overlayState === 'idle' ? 'thinking' : overlayState;
  const text = state === 'thinking' || state === 'listening' ? userInput : currentText;
  return <OverlaySurface active={overlayState !== 'idle' || sessionActive} state={state} text={text} connected={connected} words={words} activeWord={activeWord} />;
}
