import React, { useState } from 'react';
import './VerificationPrompt.css';

const VerificationPrompt = ({ 
    title, 
    message, 
    options = [], 
    operation,
    inputPlaceholder,
    onAction 
}) => {
    const [timeInput, setTimeInput] = useState('');
    
    console.log("VerificationPrompt rendered with:", { title, message, options, operation, inputPlaceholder });

    const handleOptionClick = (action) => {
        if (onAction) {
            onAction(action);
        }
    };

    const handleTimeSubmit = () => {
        if (timeInput.trim() && onAction) {
            onAction('submit_time', timeInput.trim());
            setTimeInput('');
        }
    };

    const handleKeyPress = (e) => {
        if (e.key === 'Enter') {
            handleTimeSubmit();
        }
    };

    return (
        <div className="verification-prompt-container">
            <div className="verification-header">
                <h3>{title}</h3>
            </div>
            
            <div className="verification-message">
                <p>{message}</p>
            </div>

            {inputPlaceholder && (
                <div className="time-input-section">
                    <input
                        type="text"
                        value={timeInput}
                        onChange={(e) => setTimeInput(e.target.value)}
                        onKeyPress={handleKeyPress}
                        placeholder={inputPlaceholder}
                        className="time-input"
                        autoFocus
                    />
                    <button 
                        onClick={handleTimeSubmit}
                        className="submit-time-btn"
                        disabled={!timeInput.trim()}
                    >
                        Submit
                    </button>
                </div>
            )}

            {options.length > 0 && (
                <div className="verification-actions">
                    {options.map((option, index) => (
                        <button
                            key={index}
                            onClick={() => handleOptionClick(option.action)}
                            className={`verification-btn ${option.style || 'secondary'}`}
                        >
                            {option.text}
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
};

export default VerificationPrompt; 