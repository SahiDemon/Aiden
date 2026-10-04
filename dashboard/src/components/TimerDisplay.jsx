import React, { useEffect, useMemo, useState } from 'react';
import { Clock3, Fan, Lock, Moon, Music2, Power, RotateCw, X } from 'lucide-react';
import { toast } from 'react-hot-toast';
import api from '../lib/api';

const ACTION_DETAILS = {
    shutdown: { label: 'Shut down computer', icon: Power },
    restart: { label: 'Restart computer', icon: RotateCw },
    sleep: { label: 'Put computer to sleep', icon: Moon },
    hibernate: { label: 'Hibernate computer', icon: Moon },
    lock: { label: 'Lock computer', icon: Lock },
};

const formatTime = (seconds) => {
    if (seconds <= 0) return '00:00';

    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;

    return hours > 0
        ? `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
        : `${minutes}:${secs.toString().padStart(2, '0')}`;
};

const titleCase = (value) => String(value || 'Scheduled action')
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());

const getTimerDetails = (timer) => {
    const command = timer.command_data || {};
    const params = command.params || {};
    const commandType = command.type || timer.action;

    if (commandType === 'fan_control') {
        const target = params.target || params.operation || params.action;
        const control = params.control_id || 'fan';
        const label = control === 'power' && target
            ? `Turn fan ${target}`
            : target
                ? `Set fan ${control} to ${target}`
                : 'Control fan';
        return { label, detail: 'Smart home', icon: Fan };
    }

    if (commandType === 'media_control') {
        const action = titleCase(params.action || 'Control');
        const target = titleCase(params.target || 'media');
        return { label: `${action} ${target}`, detail: 'Media', icon: Music2 };
    }

    if (ACTION_DETAILS[commandType]) {
        return { ...ACTION_DETAILS[commandType], detail: 'Computer' };
    }

    return { label: titleCase(commandType), detail: 'Scheduled action', icon: Clock3 };
};

const TimerRow = ({ timer, remaining, onCancel, cancelling }) => {
    const { label, detail, icon: Icon } = getTimerDetails(timer);
    const isImminent = remaining <= 60;

    return (
        <li className="rounded-2xl border border-white/[0.09] bg-white/[0.035] px-4 py-4 transition-colors hover:bg-white/[0.055]">
            <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-sky-300/15 bg-sky-300/[0.07] text-sky-200">
                    <Icon className="h-4 w-4" aria-hidden="true" />
                </div>
                <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold text-slate-100">{label}</p>
                    <p className="mt-0.5 text-xs text-slate-400">{detail}</p>
                </div>
                <div className="text-right">
                    <time className="block font-mono text-lg font-semibold tabular-nums tracking-tight text-sky-100">
                        {formatTime(remaining)}
                    </time>
                    <span className={`text-[11px] font-medium ${isImminent ? 'text-amber-200' : 'text-slate-500'}`}>
                        {isImminent ? 'Due shortly' : 'Scheduled'}
                    </span>
                </div>
            </div>
            <div className="mt-3 flex justify-end border-t border-white/[0.07] pt-3">
                <button
                    type="button"
                    onClick={() => onCancel(timer.id)}
                    disabled={cancelling}
                    className="rounded-lg px-2.5 py-1.5 text-xs font-medium text-slate-400 transition-colors hover:bg-rose-400/10 hover:text-rose-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-300/70 disabled:cursor-not-allowed disabled:opacity-50"
                >
                    {cancelling ? 'Cancelling…' : 'Cancel'}
                </button>
            </div>
        </li>
    );
};

const TimerDisplay = ({ timers = [], onTimerUpdate }) => {
    const [countdowns, setCountdowns] = useState({});
    const [expanded, setExpanded] = useState(false);
    const [cancellingTimerId, setCancellingTimerId] = useState(null);

    useEffect(() => {
        setCountdowns(Object.fromEntries(timers.map((timer) => [timer.id, timer.remaining_seconds])));
    }, [timers]);

    useEffect(() => {
        if (!timers.length) return undefined;

        const interval = setInterval(() => {
            setCountdowns((current) => Object.fromEntries(timers.map((timer) => [
                timer.id,
                Math.max(0, (current[timer.id] ?? timer.remaining_seconds) - 1),
            ])));
        }, 1000);

        return () => clearInterval(interval);
    }, [timers]);

    const orderedTimers = useMemo(() => [...timers].sort((a, b) => {
        const aRemaining = countdowns[a.id] ?? a.remaining_seconds;
        const bRemaining = countdowns[b.id] ?? b.remaining_seconds;
        return aRemaining - bRemaining;
    }), [countdowns, timers]);

    const handleCancelTimer = async (timerId) => {
        setCancellingTimerId(timerId);
        try {
            const response = await api.cancelTimer(timerId);
            if (!response.success) throw new Error('Cancellation failed');
            toast.success('Timer cancelled');
            onTimerUpdate?.();
        } catch (error) {
            toast.error('Could not cancel that timer');
        } finally {
            setCancellingTimerId(null);
        }
    };

    if (!timers.length) return null;

    const nextTimer = orderedTimers[0];
    const nextRemaining = countdowns[nextTimer.id] ?? nextTimer.remaining_seconds;
    const nextDetails = getTimerDetails(nextTimer);
    const NextIcon = nextDetails.icon;

    return (
        <section className="fixed left-1/2 top-5 z-50 w-[calc(100%_-_2rem)] max-w-sm -translate-x-1/2 md:left-auto md:right-6 md:top-24 md:w-80 md:translate-x-0" aria-label="Scheduled actions">
            {!expanded ? (
                <button
                    type="button"
                    onClick={() => setExpanded(true)}
                    className="group w-full rounded-2xl border border-white/[0.12] bg-[#171d29]/95 p-4 text-left shadow-[0_18px_45px_rgba(0,0,0,0.28)] backdrop-blur-md transition duration-200 hover:-translate-y-0.5 hover:border-sky-200/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-300/70 motion-reduce:transform-none"
                    aria-expanded="false"
                >
                    <div className="flex items-center gap-3">
                        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-sky-300/15 bg-sky-300/[0.07] text-sky-200">
                            <NextIcon className="h-4 w-4" aria-hidden="true" />
                        </div>
                        <div className="min-w-0 flex-1">
                            <p className="truncate text-sm font-semibold text-slate-100">{nextDetails.label}</p>
                            <p className="mt-0.5 text-xs text-slate-400">
                                {timers.length === 1 ? 'Scheduled action' : `${timers.length} scheduled actions`}
                            </p>
                        </div>
                        <time className="font-mono text-xl font-semibold tabular-nums tracking-tight text-sky-100">
                            {formatTime(nextRemaining)}
                        </time>
                    </div>
                    {nextRemaining <= 60 && (
                        <p className="mt-3 border-t border-white/[0.07] pt-3 text-xs font-medium text-amber-200">
                            Due in under a minute
                        </p>
                    )}
                </button>
            ) : (
                <div className="overflow-hidden rounded-2xl border border-white/[0.12] bg-[#171d29]/95 shadow-[0_22px_55px_rgba(0,0,0,0.34)] backdrop-blur-md">
                    <header className="flex items-center justify-between px-5 py-4">
                        <div>
                            <p className="text-sm font-semibold text-slate-100">Scheduled actions</p>
                            <p className="mt-0.5 text-xs text-slate-400">{timers.length} active {timers.length === 1 ? 'timer' : 'timers'}</p>
                        </div>
                        <button
                            type="button"
                            onClick={() => setExpanded(false)}
                            className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-white/[0.07] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-300/70"
                            aria-label="Collapse scheduled actions"
                        >
                            <X className="h-4 w-4" aria-hidden="true" />
                        </button>
                    </header>
                    <ul className="max-h-80 space-y-2 overflow-y-auto border-t border-white/[0.07] px-3 py-3" aria-live="polite">
                        {orderedTimers.map((timer) => (
                            <TimerRow
                                key={timer.id}
                                timer={timer}
                                remaining={countdowns[timer.id] ?? timer.remaining_seconds}
                                onCancel={handleCancelTimer}
                                cancelling={cancellingTimerId === timer.id}
                            />
                        ))}
                    </ul>
                </div>
            )}
        </section>
    );
};

export default TimerDisplay;
