import { useState } from 'react';
import { OverlaySurface, type WaveState } from './App';

// Vite development preview only: never connects to or triggers the assistant.
export default function OverlayPreview() {
    const [state, setState] = useState<WaveState>('listening');
    const [active, setActive] = useState(true);
    const words = 'Opening Thunder by Imagine Dragons on YouTube Music.'.split(' ').map((text, index) => ({ text, start: index * .3, end: (index + 1) * .3 }));
    return <div style={{ height: '100%', background: '#101727' }}>
        <iframe title="Dashboard backdrop" src="http://localhost:5000" style={{ border: 0, width: '100%', height: '100%' }} />
        <div style={{ position: 'fixed', inset: 0, pointerEvents: 'none' }}>
            <OverlaySurface active={active} state={state} text={state === 'thinking' ? 'Play Thunder on YouTube Music' : state === 'replying' ? 'Opening Thunder by Imagine Dragons on YouTube Music.' : 'Could you play Thunder'} words={words} activeWord={4} />
        </div>
        <div style={{ position: 'fixed', bottom: 90, left: 28, display: 'flex', gap: 8, padding: 10, background: '#101727', border: '1px solid #33445f', borderRadius: 10 }}>
            {(['listening', 'thinking', 'replying'] as WaveState[]).map(value => <button key={value} aria-pressed={state === value && active} onClick={() => { setState(value); setActive(true); }} style={{ padding: '8px 12px', background: state === value ? '#293e60' : '#172337', color: '#dce8fb', border: 0, borderRadius: 6 }}>{value}</button>)}
            <button onClick={() => setActive(!active)} style={{ background: 'transparent', color: '#afbdd0', border: 0 }}>{active ? 'Hide overlay' : 'Show overlay'}</button>
        </div>
    </div>;
}
