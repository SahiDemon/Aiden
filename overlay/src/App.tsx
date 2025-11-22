import { useState } from 'react';
import LiquidWave from './components/LiquidWave';
import './App.css';

type WaveState = 'listening' | 'thinking' | 'replying';

function App() {
  const [waveState, setWaveState] = useState<WaveState>('listening');

  return (
    <div className="app-container">
      <LiquidWave state={waveState} />

      {/* Controls for testing - positioned at bottom or draggable */}
      <div className="controls">
        <button onClick={() => setWaveState('listening')} disabled={waveState === 'listening'}>
          Listening
        </button>
        <button onClick={() => setWaveState('thinking')} disabled={waveState === 'thinking'}>
          Thinking
        </button>
        <button onClick={() => setWaveState('replying')} disabled={waveState === 'replying'}>
          Replying
        </button>
      </div>
    </div>
  );
}

export default App;
