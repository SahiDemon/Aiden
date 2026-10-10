import { useMemo } from 'react';
import type { SpeechWord } from '../hooks/useWebSocket';

type VoiceState = 'listening' | 'thinking' | 'replying';
interface LiquidWaveProps { state: VoiceState; displayText?: string; words?: SpeechWord[]; activeWord?: number }
const labels = { listening: 'Listening', thinking: 'Thinking', replying: 'Speaking' };

export default function LiquidWave({ state, displayText, words = [], activeWord = -1 }: LiquidWaveProps) {
    const captions = useMemo(() => {
        const text = displayText || '';
        let cursor = 0;
        const starts: number[] = [];
        const lowerText = text.toLowerCase();
        for (const word of words) {
            const index = lowerText.indexOf(word.text.toLowerCase(), cursor);
            if (index >= 0) cursor = index + word.text.length;
            starts.push(index);
        }
        if (starts.some(index => index < 0)) return words.map(word => word.text);
        return starts.map((index, word) => text.slice(word === 0 ? 0 : index, starts[word + 1] ?? text.length).trim());
    }, [displayText, words]);
    const start = Math.max(0, activeWord - 5);
    const end = Math.min(words.length, Math.max(12, activeWord + 8));
    const timedText = state === 'replying' && words.length > 0;
    return <div className={`voice-capsule state-${state}`} role="status" aria-live="polite">
        <div className="voice-emblem" aria-hidden="true">a</div>
        <div className="voice-copy">
            <div className="voice-heading"><span>Aiden</span><span className="voice-state"><i />{labels[state]}</span></div>
            <p className={displayText ? 'voice-transcript' : 'voice-prompt'}>{timedText ? <>{start > 0 && '… '}{words.slice(start, end).map((word, index) => <span key={start + index} className={start + index === activeWord ? 'spoken-word current' : start + index < activeWord ? 'spoken-word spoken' : 'spoken-word'}>{captions[start + index] || word.text}{' '}</span>)}{end < words.length && ' …'}</> : displayText || (state === 'listening' ? 'Go ahead. I’m here.' : state === 'thinking' ? 'Making the connections…' : 'Here’s what I found.')}</p>
        </div>
        <div className="voice-wave" aria-hidden="true">{[0,1,2,3,4,5,6].map(index => <i key={index} style={{ animationDelay: `${index * -0.13}s` }} />)}</div>
    </div>;
}
