import React, { useState, useEffect } from 'react';
import './ScheduledCommands.css';

const ScheduledCommands = ({ schedules = [], onCancelSchedule, onModifySchedule }) => {
    const [countdowns, setCountdowns] = useState({});

    useEffect(() => {
        // Initialize countdowns from incoming schedules
        const initialCountdowns = {};
        schedules.forEach(schedule => {
            initialCountdowns[schedule.task_id] = schedule.remaining_seconds;
        });
        setCountdowns(initialCountdowns);
    }, [schedules]);

    useEffect(() => {
        const interval = setInterval(() => {
            setCountdowns(prev => {
                const newCountdowns = {};
                let hasActiveSchedules = false;
                
                schedules.forEach(schedule => {
                    const currentCountdown = prev[schedule.task_id] ?? schedule.remaining_seconds;
                    const newValue = Math.max(0, currentCountdown - 1);
                    newCountdowns[schedule.task_id] = newValue;
                    if (newValue > 0) hasActiveSchedules = true;
                });
                
                // Only update if there are active schedules
                return hasActiveSchedules ? newCountdowns : prev;
            });
        }, 1000);

        return () => clearInterval(interval);
    }, [schedules]);

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

    const getOperationIcon = (operation) => {
        switch (operation) {
            case 'shutdown':
                return '⚡';
            case 'restart':
                return '🔄';
            case 'sleep':
                return '😴';
            case 'hibernate':
                return '🥶';
            case 'lock':
                return '🔒';
            default:
                return '⚙️';
        }
    };

    const getOperationColor = (operation) => {
        switch (operation) {
            case 'shutdown':
                return '#ff4757';
            case 'restart':
                return '#ffa502';
            case 'sleep':
                return '#3742fa';
            case 'hibernate':
                return '#5f27cd';
            case 'lock':
                return '#00d2d3';
            default:
                return '#747d8c';
        }
    };

    const getUrgencyClass = (seconds) => {
        if (seconds <= 60) return 'urgent';
        if (seconds <= 300) return 'warning';
        return 'normal';
    };

    if (!schedules || schedules.length === 0) {
        return (
            <div className="scheduled-commands-container">
                <div className="no-schedules">
                    <div className="no-schedules-icon">⏰</div>
                    <p>No scheduled commands</p>
                </div>
            </div>
        );
    }

    return (
        <div className="scheduled-commands-container">
            <div className="scheduled-commands-header">
                <h3>⏱️ Active Schedules</h3>
                <span className="schedule-count">{schedules.length}</span>
            </div>
            
            <div className="schedules-list">
                {schedules.map(schedule => {
                    const currentCountdown = countdowns[schedule.task_id] ?? schedule.remaining_seconds;
                    const urgencyClass = getUrgencyClass(currentCountdown);
                    
                    return (
                        <div key={schedule.task_id} className={`schedule-item ${urgencyClass}`}>
                            <div className="schedule-header">
                                <div className="operation-info">
                                    <span 
                                        className="operation-icon"
                                        style={{ color: getOperationColor(schedule.operation) }}
                                    >
                                        {getOperationIcon(schedule.operation)}
                                    </span>
                                    <span className="operation-name">
                                        {schedule.operation.charAt(0).toUpperCase() + schedule.operation.slice(1)}
                                    </span>
                                </div>
                                
                                <div className="countdown-display">
                                    <span className={`countdown-time ${urgencyClass}`}>
                                        {formatTime(currentCountdown)}
                                    </span>
                                </div>
                            </div>
                            
                            <div className="schedule-details">
                                <div className="execution-time">
                                    Executing at: {schedule.execution_time}
                                </div>
                                <div className="original-query">
                                    "{schedule.original_query}"
                                </div>
                            </div>
                            
                            <div className="schedule-actions">
                                <button 
                                    className="action-btn modify-btn"
                                    onClick={() => onModifySchedule && onModifySchedule(schedule.task_id)}
                                    title="Modify time"
                                >
                                    ⏱️ Modify
                                </button>
                                <button 
                                    className="action-btn cancel-btn"
                                    onClick={() => onCancelSchedule && onCancelSchedule(schedule.task_id)}
                                    title="Cancel schedule"
                                >
                                    ✕ Cancel
                                </button>
                            </div>
                            
                            {currentCountdown <= 60 && (
                                <div className="urgency-banner">
                                    <span>⚠️ Executing soon!</span>
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>
            
            <div className="schedules-footer">
                <button 
                    className="footer-btn cancel-all-btn"
                    onClick={() => onCancelSchedule && onCancelSchedule('all')}
                >
                    Cancel All Schedules
                </button>
            </div>
        </div>
    );
};

export default ScheduledCommands; 