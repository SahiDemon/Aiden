import React, { useState, useEffect } from 'react';
import { X, Clock, AlertTriangle, Power } from 'lucide-react';
import api from '../lib/api';
import { toast } from 'react-hot-toast';

const TimerDisplay = ({ timers = [], onTimerUpdate }) => {
    const [countdowns, setCountdowns] = useState({});
    const [expanded, setExpanded] = useState(false);

    // Update countdowns from incoming timers
    useEffect(() => {
        const initialCountdowns = {};
        timers.forEach(timer => {
            initialCountdowns[timer.id] = timer.remaining_seconds;
        });
        setCountdowns(initialCountdowns);
    }, [timers]);

    // Countdown interval
    useEffect(() => {
        if (timers.length === 0) return;

        const interval = setInterval(() => {
            setCountdowns(prev => {
                const newCountdowns = {};
                
                timers.forEach(timer => {
                    const currentCountdown = prev[timer.id] ?? timer.remaining_seconds;
                    const newValue = Math.max(0, currentCountdown - 1);
                    newCountdowns[timer.id] = newValue;
                });
                
                // Always return updated countdowns to properly display zero values
                return newCountdowns;
            });
        }, 1000);

        return () => clearInterval(interval);
    }, [timers]);

    const formatTime = (seconds) => {
        if (seconds <= 0) return "00:00";
        
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = seconds % 60;
        
        if (hours > 0) {
            return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
        }
        return `${minutes}:${secs.toString().padStart(2, '0')}`;
    };

    const getActionIcon = (action) => {
        switch (action) {
            case 'shutdown':
                return <Power className="w-4 h-4" />;
            case 'restart':
                return <Power className="w-4 h-4" />;
            case 'sleep':
                return <Power className="w-4 h-4" />;
            case 'hibernate':
                return <Power className="w-4 h-4" />;
            case 'lock':
                return <Power className="w-4 h-4" />;
            default:
                return <Clock className="w-4 h-4" />;
        }
    };

    const getActionColor = (action) => {
        switch (action) {
            case 'shutdown':
                return { bg: 'bg-red-500/20', border: 'border-red-400/40', text: 'text-red-300', icon: 'text-red-400' };
            case 'restart':
                return { bg: 'bg-orange-500/20', border: 'border-orange-400/40', text: 'text-orange-300', icon: 'text-orange-400' };
            case 'sleep':
                return { bg: 'bg-blue-500/20', border: 'border-blue-400/40', text: 'text-blue-300', icon: 'text-blue-400' };
            case 'hibernate':
                return { bg: 'bg-purple-500/20', border: 'border-purple-400/40', text: 'text-purple-300', icon: 'text-purple-400' };
            case 'lock':
                return { bg: 'bg-cyan-500/20', border: 'border-cyan-400/40', text: 'text-cyan-300', icon: 'text-cyan-400' };
            default:
                return { bg: 'bg-gray-500/20', border: 'border-gray-400/40', text: 'text-gray-300', icon: 'text-gray-400' };
        }
    };

    const getUrgencyBorder = (seconds) => {
        if (seconds <= 60) return 'border-red-400/60 shadow-red-400/20';
        if (seconds <= 300) return 'border-orange-400/50 shadow-orange-400/15';
        return 'border-blue-400/40 shadow-blue-400/10';
    };

    const handleCancelTimer = async (timerId) => {
        try {
            const response = await api.cancelTimer(timerId);
            if (response.success) {
                toast.success('Timer cancelled');
                setCountdowns(prev => {
                    const newCountdowns = { ...prev };
                    delete newCountdowns[timerId];
                    return newCountdowns;
                });
                onTimerUpdate?.();
            } else {
                toast.error('Failed to cancel timer');
            }
        } catch (error) {
            toast.error('Error cancelling timer');
            console.error('Cancel timer error:', error);
        }
    };

    const handleCancelAllTimers = async () => {
        try {
            const response = await api.cancelAllTimers();
            if (response.success) {
                toast.success('All timers cancelled');
                setCountdowns({});
                onTimerUpdate?.();
            } else {
                toast.error('Failed to cancel timers');
            }
        } catch (error) {
            toast.error('Error cancelling timers');
            console.error('Cancel all timers error:', error);
        }
    };

    // Don't render if no timers
    if (!timers || timers.length === 0) {
        return null;
    }

    // Get the most urgent timer for compact display
    const urgentTimer = timers.reduce((most, current) => {
        const currentRemaining = countdowns[current.id] ?? current.remaining_seconds;
        const mostRemaining = countdowns[most.id] ?? most.remaining_seconds;
        return currentRemaining < mostRemaining ? current : most;
    }, timers[0]);

    const urgentRemaining = countdowns[urgentTimer.id] ?? urgentTimer.remaining_seconds;
    const urgentColors = getActionColor(urgentTimer.action);
    const urgentBorder = getUrgencyBorder(urgentRemaining);

    return (
        <div className="timer-display-container">
            {/* Compact Timer Display */}
            <div 
                className={`timer-compact liquid-glass-card cursor-pointer transition-all duration-300 hover:scale-105 ${urgentBorder}`}
                onClick={() => setExpanded(!expanded)}
                style={{
                    backdropFilter: 'blur(12px)',
                    background: 'rgba(255, 255, 255, 0.05)',
                    boxShadow: urgentRemaining <= 60 ? 
                        '0 0 20px rgba(239, 68, 68, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.1)' :
                        '0 8px 32px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.1)'
                }}
            >
                <div className="flex items-center gap-4 p-4">
                    <div className={`w-10 h-10 rounded-xl ${urgentColors.bg} ${urgentColors.border} border flex items-center justify-center ${urgentColors.icon}`}>
                        {getActionIcon(urgentTimer.action)}
                    </div>
                    <div className="flex-1">
                        <div className="text-sm font-medium text-white/90 uppercase tracking-wider mb-1">
                            {urgentTimer.action}
                        </div>
                        <div className={`text-lg font-mono font-bold ${urgentColors.text}`}>
                            {formatTime(urgentRemaining)}
                        </div>
                    </div>
                    {timers.length > 1 && (
                        <div className="bg-blue-500/20 border border-blue-400/30 text-blue-200 text-sm px-3 py-1 rounded-lg">
                            +{timers.length - 1}
                        </div>
                    )}
                </div>
                {urgentRemaining <= 60 && (
                    <div className="px-4 pb-4">
                        <div className="flex items-center gap-2 text-sm text-red-300 bg-red-500/10 border border-red-400/20 rounded-lg px-3 py-2">
                            <AlertTriangle className="w-4 h-4" />
                            Executing soon
                        </div>
                    </div>
                )}
            </div>

            {/* Expanded Timer List */}
            {expanded && (
                <div 
                    className="timer-expanded liquid-glass-card mt-4"
                    style={{
                        backdropFilter: 'blur(12px)',
                        background: 'rgba(255, 255, 255, 0.05)',
                        boxShadow: '0 20px 40px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.1)'
                    }}
                >
                    <div className="flex items-center justify-between p-6 border-b border-white/10">
                        <h3 className="text-lg font-semibold text-white flex items-center gap-3">
                            <Clock className="w-5 h-5 text-blue-400" />
                            Active Timers ({timers.length})
                        </h3>
                        <button
                            onClick={() => setExpanded(false)}
                            className="text-white/50 hover:text-white/80 transition-colors p-2 hover:bg-white/10 rounded-lg"
                        >
                            <X className="w-5 h-5" />
                        </button>
                    </div>
                    
                    <div className="p-6 space-y-4 max-h-80 overflow-y-auto">
                        {timers.map(timer => {
                            const remaining = countdowns[timer.id] ?? timer.remaining_seconds;
                            const colors = getActionColor(timer.action);
                            const borderClass = getUrgencyBorder(remaining);
                            
                            return (
                                <div 
                                    key={timer.id} 
                                    className={`timer-item bg-white/5 rounded-xl p-5 border transition-all duration-300 hover:bg-white/8 ${borderClass}`}
                                    style={{
                                        boxShadow: remaining <= 60 ? 
                                            '0 0 15px rgba(239, 68, 68, 0.15)' :
                                            '0 4px 20px rgba(0, 0, 0, 0.2)'
                                    }}
                                >
                                    <div className="flex items-center justify-between">
                                        <div className="flex items-center gap-4">
                                            <div className={`w-12 h-12 rounded-xl ${colors.bg} ${colors.border} border flex items-center justify-center ${colors.icon}`}>
                                                {getActionIcon(timer.action)}
                                            </div>
                                            <div>
                                                <div className="text-base font-medium text-white capitalize mb-1">
                                                    {timer.action}
                                                </div>
                                                <div className={`text-xl font-mono font-bold ${colors.text}`}>
                                                    {formatTime(remaining)}
                                                </div>
                                            </div>
                                        </div>
                                        
                                        <button
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                handleCancelTimer(timer.id);
                                            }}
                                            className="bg-red-500/20 hover:bg-red-500/30 border border-red-400/40 text-red-300 px-6 py-3 rounded-xl text-sm font-medium transition-all duration-200 hover:scale-105"
                                        >
                                            Cancel
                                        </button>
                                    </div>
                                    
                                    {remaining <= 60 && (
                                        <div className="mt-4 pt-4 border-t border-white/10">
                                            <div className="flex items-center gap-2 text-sm text-red-300">
                                                <AlertTriangle className="w-4 h-4" />
                                                System will execute this action in less than 1 minute
                                            </div>
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                    
                    {timers.length > 1 && (
                        <div className="p-6 border-t border-white/10">
                            <button
                                onClick={handleCancelAllTimers}
                                className="w-full bg-red-500/20 hover:bg-red-500/30 border border-red-400/40 text-red-300 px-6 py-4 rounded-xl text-base font-medium transition-all duration-200 hover:scale-105"
                            >
                                Cancel All Timers
                            </button>
                        </div>
                    )}
                </div>
            )}

            <style jsx>{`
                .timer-display-container {
                    position: fixed;
                    top: 14rem;
                    right: 1.5rem;
                    z-index: 999;
                    min-width: 320px;
                    max-width: 400px;
                }
                
                .timer-compact {
                    border-radius: 1rem;
                    border: 1px solid;
                }
                
                .timer-expanded {
                    border-radius: 1rem;
                    border: 1px solid rgba(255, 255, 255, 0.15);
                }
                
                .timer-item {
                    border-width: 1px;
                }
                
                /* Custom scrollbar for timer list */
                .timer-expanded div::-webkit-scrollbar {
                    width: 6px;
                }
                
                .timer-expanded div::-webkit-scrollbar-track {
                    background: rgba(255, 255, 255, 0.1);
                    border-radius: 3px;
                }
                
                .timer-expanded div::-webkit-scrollbar-thumb {
                    background: rgba(255, 255, 255, 0.3);
                    border-radius: 3px;
                }
                
                .timer-expanded div::-webkit-scrollbar-thumb:hover {
                    background: rgba(255, 255, 255, 0.4);
                }
            `}</style>
        </div>
    );
};

export default TimerDisplay;