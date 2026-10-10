import { useState, useEffect, useCallback, useRef } from 'react';

export const useWebSpeech = ({ onResult, onEnd, onError, onStart }) => {
  const [isSupported, setIsSupported] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [recognition, setRecognition] = useState(null);

  const callbacksRef = useRef({ onResult, onEnd, onError, onStart });
  
  // Keep callbacks fresh without triggering effect
  useEffect(() => {
    callbacksRef.current = { onResult, onEnd, onError };
  }, [onResult, onEnd, onError, onStart]);

  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      setIsSupported(true);
      const rec = new SpeechRecognition();
      rec.continuous = false;
      rec.interimResults = true;
      rec.lang = 'en-US';

      rec.onstart = () => {
        setIsRecording(true);
        callbacksRef.current.onStart?.();
      };

      rec.onresult = (event) => {
        let interimTranscript = '';
        let finalTranscript = '';

        for (let i = event.resultIndex; i < event.results.length; ++i) {
          if (event.results[i].isFinal) {
            finalTranscript += event.results[i][0].transcript;
          } else {
            interimTranscript += event.results[i][0].transcript;
          }
        }
        
        if (callbacksRef.current.onResult) {
          callbacksRef.current.onResult(interimTranscript, finalTranscript);
        }
      };

      rec.onerror = (event) => {
        console.error('Speech recognition error', event.error);
        if (callbacksRef.current.onError) callbacksRef.current.onError(event.error);
        setIsRecording(false);
      };

      rec.onend = () => {
        setIsRecording(false);
        if (callbacksRef.current.onEnd) callbacksRef.current.onEnd();
      };

      setRecognition(rec);
      
      return () => {
        // Cleanup the old instance when unmounting
        rec.onstart = null;
        rec.onresult = null;
        rec.onerror = null;
        rec.onend = null;
        try { rec.abort(); } catch(e) {}
      }
    }
  }, []);

  const startRecording = useCallback(() => {
    if (recognition && !isRecording) {
      try {
        recognition.start();
      } catch (e) {
        console.error('Error starting recognition:', e);
        callbacksRef.current.onError?.('could not start recording');
      }
    }
  }, [recognition, isRecording]);

  const stopRecording = useCallback(() => {
    if (recognition && isRecording) {
      try {
        recognition.stop();
      } catch (e) {
        console.error('Error stopping recognition:', e);
      }
    }
  }, [recognition, isRecording]);

  return {
    isSupported,
    isRecording,
    startRecording,
    stopRecording
  };
};
