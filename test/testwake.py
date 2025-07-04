
import speech_recognition as sr
import difflib

def main():
    """
    Main function to run the speech recognition loop.
    """
    # --- Configuration ---
    WAKE_WORD = "aiden"
    # The similarity threshold has been lowered to allow for more detections.
    # A lower value like 0.65 makes the recognition more lenient and will
    # likely accept words like "hidden" (score ~0.73) again.
    SIMILARITY_THRESHOLD = 0.65

    # Initialize the recognizer
    recognizer = sr.Recognizer()

    # Use the default microphone as the audio source
    microphone = sr.Microphone()

    print("Script started. I am now listening...")
    print(f"Wake Word: '{WAKE_WORD}', Similarity Threshold: {SIMILARITY_THRESHOLD}")
    print("Say your wake word to see the recognition and similarity score.")
    print("Press Ctrl+C to stop the script.")

    # Calibrate the recognizer to the ambient noise level for better accuracy.
    with microphone as source:
        print("\nCalibrating for ambient noise, please wait...")
        recognizer.adjust_for_ambient_noise(source, duration=1)
        print("Calibration complete. Listening for speech...")

    # Loop continuously to listen for speech
    while True:
        try:
            with microphone as source:
                # Listen for the first phrase and extract it into audio data
                audio = recognizer.listen(source)

            # Recognize speech using Google Web Speech API
            print("\nProcessing audio...")
            recognized_text = recognizer.recognize_google(audio).lower()
            words = recognized_text.split()

            if not words:
                print("...(Could not understand the audio, listening again)...")
                continue

            # Find the word in the phrase with the highest similarity to the wake word.
            # This is more precise than checking the whole phrase.
            scores = [difflib.SequenceMatcher(None, word, WAKE_WORD).ratio() for word in words]
            best_match_score = max(scores)
            best_match_word = words[scores.index(best_match_score)]

            print(f'I heard: "{recognized_text}"')
            print(f'Best match in phrase: "{best_match_word}" with similarity: {best_match_score:.2f}')

            # Check if the best match is good enough to be considered the wake word
            if best_match_score > SIMILARITY_THRESHOLD:
                print(f">>> WAKE WORD '{WAKE_WORD}' DETECTED! <<<")

        except sr.UnknownValueError:
            # This error means the recognizer could not understand the audio.
            print("...(Could not understand the audio, listening again)...")
        except sr.RequestError as e:
            # This error means there was a problem with the Google API request.
            print(f"API Error: Could not request results from Google Speech Recognition service; {e}")
            break # Exit the loop if the service is unavailable
        except KeyboardInterrupt:
            # Allows the user to stop the script with Ctrl+C
            print("\nScript stopped by user.")
            break

if __name__ == "__main__":
    main()
