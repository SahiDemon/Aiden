import { AnimatePresence, motion } from 'framer-motion';
import { useWebSocket } from './hooks/useWebSocket';
import LiquidWave from './components/LiquidWave';
import './App.css';

type WaveState = 'listening' | 'thinking' | 'replying';

function App() {
  const { connected, overlayState, currentText, userInput } = useWebSocket();

  // Only show overlay when state is active (not idle)
  const shouldShowOverlay = overlayState !== 'idle';
  const waveState: WaveState = overlayState === 'idle' ? 'listening' : overlayState as WaveState;

  // Determine which text to display
  const displayText = overlayState === 'thinking' || overlayState === 'listening'
    ? userInput
    : currentText;

  return (
    <div className="app-container">
      <AnimatePresence mode="wait">
        {shouldShowOverlay && (
          <motion.div
            key="overlay"
            initial={{ opacity: 0, y: -100 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -100 }}
            transition={{ duration: 0.4, ease: "easeInOut" }}
          >
            <LiquidWave state={waveState} displayText={displayText} />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Connection indicator - only show when disconnected */}
      {!connected && (
        <div className="connection-status">
          <div className="status-dot disconnected"></div>
          <span>Connecting to Aiden...</span>
        </div>
      )}
    </div>
  );
}

export default App;
