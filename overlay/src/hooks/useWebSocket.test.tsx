import { act, useEffect } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { beforeEach, afterEach, test, expect, vi } from 'vitest';
import { useWebSocket } from './useWebSocket';

let result: ReturnType<typeof useWebSocket>;
let root: Root;
let container: HTMLDivElement;

const ipc = vi.fn();
class FakeSocket {
    static OPEN = 1;
    static latest: FakeSocket;
    readyState = 0;
    onopen: (() => void) | null = null;
    onclose: (() => void) | null = null;
    onerror: (() => void) | null = null;
    onmessage: ((event: { data: string }) => void) | null = null;
    send = vi.fn();
    close = vi.fn();
    constructor() { FakeSocket.latest = this; }
}
function Probe() { const state = useWebSocket('ws://test'); useEffect(() => { result = state; }, [state]); return null; }
function receive(type: string, data: object) { act(() => FakeSocket.latest.onmessage?.({ data: JSON.stringify({ type, data }) })); }
function voice(status: string, extra: object = {}) { receive('voice_activity', { status, speaking: false, ...extra }); }
beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
    vi.stubGlobal('WebSocket', FakeSocket);
    Object.defineProperty(window, 'ipcRenderer', { configurable: true, value: { send: ipc } });
    ipc.mockClear();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => root.render(<Probe />));
    act(() => { FakeSocket.latest.readyState = 1; FakeSocket.latest.onopen?.(); });
});
afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.useRealTimers();
    vi.unstubAllGlobals();
});

test('capture end transitions to thinking, playback starts speaking, completion hides', () => {
    voice('listening', { active: true });
    expect(result.overlayState).toBe('listening');
    receive('message', { role: 'user', content: 'Play Thunder', source: 'local' });
    voice('idle'); // Actual STT handoff event.
    expect(result.overlayState).toBe('thinking');
    expect(result.sessionActive).toBe(true);
    expect(result.userInput).toBe('Play Thunder');
    voice('processing', { active: true });
    expect(result.overlayState).toBe('thinking');
    receive('assistant_speaking', { text: 'Opening Thunder' });
    expect(result.overlayState).toBe('replying');
    expect(result.currentText).toBe('Opening Thunder');
    voice('idle'); // Actual TTS completion event.
    expect(result.overlayState).toBe('idle');
    expect(result.sessionActive).toBe(false);
    expect(result.currentText).toBe('');
    act(() => vi.advanceTimersByTime(700));
    expect(ipc).toHaveBeenCalledWith('overlay:hide');
});

test('explicit cancellation wins and a new listening turn clears old text', () => {
    receive('assistant_speaking', { text: 'Old reply' });
    voice('speaking', { speaking: true, active: false });
    expect(result.overlayState).toBe('idle');
    voice('listening', { active: true });
    expect(result.overlayState).toBe('listening');
    expect(result.currentText).toBe('');
    expect(result.userInput).toBe('');
    ipc.mockClear();
    act(() => vi.advanceTimersByTime(700));
    expect(ipc).not.toHaveBeenCalledWith('overlay:hide');
});

test('speaking status alone is sufficient, active idle handoffs stay thinking', () => {
    voice('speaking');
    expect(result.overlayState).toBe('replying');
    voice('idle', { active: true });
    expect(result.overlayState).toBe('thinking');
    voice('idle', { active: false });
    expect(result.overlayState).toBe('idle');
});

test('typed chat cannot trigger any overlay stage or contaminate voice text', () => {
    receive('message', { role: 'user', source: 'web_text', content: 'Typed question' });
    receive('message', { role: 'assistant', source: 'web_text', content: 'Typed answer' });
    voice('processing', { active: true, source: 'web_text' });
    receive('assistant_speaking', { source: 'web_text', text: 'Typed answer' });
    expect(result.overlayState).toBe('idle');
    expect(result.sessionActive).toBe(false);
    expect(result.currentText).toBe('');
    expect(result.userInput).toBe('');
    expect(ipc).not.toHaveBeenCalledWith('overlay:raise');
});

test('disconnect clears active stages and reconnects without replaying stale text', () => {
    receive('assistant_speaking', { text: 'Previous turn' });
    const previousSocket = FakeSocket.latest;
    act(() => { FakeSocket.latest.readyState = 3; FakeSocket.latest.onclose?.(); });
    expect(result.overlayState).toBe('idle');
    expect(result.connected).toBe(false);
    expect(result.currentText).toBe('');
    act(() => vi.advanceTimersByTime(1000));
    expect(FakeSocket.latest).not.toBe(previousSocket);
    act(() => { FakeSocket.latest.readyState = 1; FakeSocket.latest.onopen?.(); });
    expect(result.connected).toBe(true);
    expect(result.overlayState).toBe('idle');
});

test('unmount cancels reconnect, heartbeat, and late FakeSocket.latest callbacks', () => {
    act(() => root.unmount());
    expect(FakeSocket.latest.onmessage).toBeNull();
    expect(FakeSocket.latest.onopen).toBeNull();
    expect(vi.getTimerCount()).toBe(0);
    root = createRoot(container);
});

test('live captions update only the listening turn and ignore silent text', () => {
    receive('voice_transcript', { text: 'stale preview', source: 'local' });
    expect(result.userInput).toBe('');
    voice('listening');
    receive('voice_transcript', { text: 'play', source: 'local' });
    expect(result.userInput).toBe('play');
    receive('voice_transcript', { text: 'play Thunder', source: 'web' });
    expect(result.userInput).toBe('play');
    receive('voice_transcript', { text: 'silent text', source: 'web_text' });
    expect(result.userInput).toBe('play');
    voice('processing');
    receive('voice_transcript', { text: 'late preview', source: 'local' });
    expect(result.userInput).toBe('play');
});

test('spoken words follow audio boundaries and reject stale speech IDs', () => {
    const words = [{ text: 'Hello', start: 0, end: .4 }, { text: 'there', start: .5, end: 1 }];
    receive('assistant_speaking', { text: 'Hello there', speech_id: 'turn1', words });
    receive('tts_progress', { speech_id: 'turn1', position: .2, state: 'progress' });
    expect(result.activeWord).toBe(0);
    receive('tts_progress', { speech_id: 'old', position: .6, state: 'progress' });
    expect(result.activeWord).toBe(0);
    receive('tts_progress', { speech_id: 'turn1', position: .6, state: 'progress' });
    expect(result.activeWord).toBe(1);
    voice('idle', { active: false });
    receive('tts_progress', { speech_id: 'turn1', position: .6, source: 'web', state: 'playing' });
    expect(result.overlayState).toBe('idle');
});

test.each(['web', 'web_text'])('browser %s requests never show the PC overlay', source => {
    voice('listening', { active: true, source });
    receive('voice_transcript', { text: 'Browser question', source });
    receive('message', { role: 'user', content: 'Browser question', source });
    voice('processing', { active: true, source });
    receive('assistant_speaking', { text: 'Hello', source, speech_id: 'browser', words: [{ text: 'Hello', start: 0, end: 1 }] });
    receive('message', { role: 'assistant', content: 'Hello', source });
    for (const state of ['blocked', 'playing', 'progress', 'ended']) {
        receive('tts_progress', { speech_id: 'browser', source, state, position: .1 });
    }
    voice('idle', { active: false, source });
    expect(result.overlayState).toBe('idle');
    expect(result.sessionActive).toBe(false);
    expect(result.currentText).toBe('');
    expect(result.userInput).toBe('');
    expect(result.words).toEqual([]);
    expect(ipc).not.toHaveBeenCalledWith('overlay:raise');
});

test('browser events do not interrupt an ongoing PC conversation', () => {
    receive('assistant_speaking', { text: 'PC reply', source: 'local', speech_id: 'pc', words: [{ text: 'PC', start: 0, end: 1 }] });
    ipc.mockClear();
    voice('processing', { active: true, source: 'web' });
    receive('assistant_speaking', { text: 'Browser reply', source: 'web', speech_id: 'browser' });
    receive('tts_progress', { speech_id: 'pc', source: 'web', state: 'ended', position: 1 });
    voice('idle', { active: false, source: 'web' });
    expect(result.overlayState).toBe('replying');
    expect(result.currentText).toBe('PC reply');
    expect(result.sessionActive).toBe(true);
    expect(ipc).not.toHaveBeenCalled();
    receive('tts_progress', { speech_id: 'pc', source: 'local', state: 'progress', position: .1 });
    expect(result.activeWord).toBe(0);
    receive('tts_progress', { speech_id: 'pc', source: 'local', state: 'ended', position: 1 });
    expect(result.overlayState).toBe('idle');
});
