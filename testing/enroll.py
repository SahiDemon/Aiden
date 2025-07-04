# enroll.py
import sounddevice as sd
import numpy as np
import librosa
from scipy.io.wavfile import write
import os

# --- Configuration ---
WAKE_WORD_NAME = "aiden"
NUM_RECORDINGS = 5
SAMPLE_RATE = 16000  # 16kHz sample rate
DURATION = 2  # 2 seconds for each recording
REFERENCE_FILE = "wake_word_ref.npy"
RECORDINGS_DIR = "recordings"

def record_audio(filename, duration, sample_rate):
    """Records audio from the microphone and saves it to a file."""
    print(f"Recording for {duration} seconds... Speak your wake word now.")
    
    # Record audio
    audio_data = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1, dtype='float32')
    sd.wait()  # Wait until recording is finished
    
    # Save as WAV file
    write(filename, sample_rate, audio_data)
    print(f"Recording saved to {filename}")

def create_reference_template():
    """
    Guides the user through recording wake word samples and creates an MFCC reference template.
    """
    if not os.path.exists(RECORDINGS_DIR):
        os.makedirs(RECORDINGS_DIR)

    mfccs = []
    
    # --- Recording Phase ---
    print(f"--- Wake Word Enrollment for '{WAKE_WORD_NAME}' ---")
    print(f"You will be asked to say the wake word {NUM_RECORDINGS} times.")
    input("Press Enter to start...")

    for i in range(NUM_RECORDINGS):
        file_path = os.path.join(RECORDINGS_DIR, f"rec_{i+1}.wav")
        record_audio(file_path, DURATION, SAMPLE_RATE)
        
        # --- Feature Extraction ---
        # Load the just-recorded audio file
        audio, sr = librosa.load(file_path, sr=SAMPLE_RATE)
        
        # Extract MFCCs
        # n_mfcc is the number of coefficients to return
        # hop_length is the number of samples between successive frames
        # n_fft is the length of the FFT window
        mfcc = librosa.feature.mfcc(y=audio, sr=sr, n_mfcc=13, n_fft=512, hop_length=256)
        mfccs.append(mfcc)
        
        if i < NUM_RECORDINGS - 1:
            input("Press Enter for the next recording...")

    # --- Template Creation ---
    print("\nAll recordings complete. Creating reference template...")

    # Pad or truncate MFCCs to have the same length
    min_len = min(m.shape[1] for m in mfccs)
    aligned_mfccs = [m[:, :min_len] for m in mfccs]
    
    # Average the MFCCs to create a single reference template
    reference_template = np.mean(aligned_mfccs, axis=0)

    # Save the reference template to a file
    np.save(REFERENCE_FILE, reference_template)
    print(f"Reference template saved to '{REFERENCE_FILE}'")
    print("Enrollment complete!")


if __name__ == "__main__":
    create_reference_template()