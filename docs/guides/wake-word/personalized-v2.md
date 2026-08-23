# Personalized Aiden wake detection v2

The v2 path accepts both **Aiden** and **Hey Aiden**, filters detections with a
personal verifier, and retains speech spoken immediately after the wake phrase.
The existing `vosk_models/hey_aiden.onnx` remains the automatic rollback model.

Recordings, generated data, calibration profiles, and model binaries stay under
ignored `.local/` or `vosk_models/` paths. Do not add them to Git.

## 1. Record the local dataset

Stop Aiden so it releases the microphone, activate the normal app environment,
and run:

```powershell
python scripts/diagnostics/record_wake_word_dataset.py
```

This records 12 examples of each wake phrase, the hard-negative phrases, 60
seconds of ordinary speech, and 30 seconds of room/TV/music sound. To record the
separate 48-activation acceptance matrix later, run:

```powershell
python scripts/diagnostics/record_wake_word_dataset.py --acceptance-only
```

## 2. Train the base model on the RTX 5070

Training is isolated from Aiden's Python 3.13 runtime. It requires WSL2 with
CUDA access and Python 3.10 installed. The first run downloads a large public
feature set, so keep at least 25 GB free.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/diagnostics/train_wake_word_v2.ps1
```

The configuration generates 30,000 training and 3,000 validation examples,
uses both target phrases, includes the hard negatives, trains the official
32-unit DNN architecture, and targets 0.2 false positives per hour during base
model training.

## 3. Train the personal verifier and calibrate

Run these in the normal Aiden environment after `aiden_v2.onnx` exists:

```powershell
python scripts/diagnostics/train_personal_verifier.py
python scripts/diagnostics/calibrate_wake_word_v2.py
```

Calibration searches thresholds using held-out recordings. It requires zero
hard-negative activations and no more than 0.125 estimated false positives per
hour. If the separate 48 samples exist, the profile also reports the acceptance
recall targets and whether it is deployment-ready.

## 4. Shadow evaluation and activation

Run the local eight-hour evaluation while normal conversation, TV, music, and
room sound are present. It stores scores and timestamps, never raw audio:

```powershell
python scripts/diagnostics/run_wake_word_shadow.py --hours 8
```

Only after the report passes, set:

```dotenv
SPEECH_OWW_PROFILE_PATH=.local/wake-word/profile.json
SPEECH_OWW_SHADOW_MODE=false
```

For in-app observation before enabling callbacks, set
`SPEECH_OWW_SHADOW_MODE=true`. Near-miss logs include base score, verifier score,
Silero VAD, RMS, model, latency, and smoothing hits. Raw diagnostic clips are
saved only when `SPEECH_OWW_CAPTURE_DIAGNOSTICS=true`.

If the v2 model or verifier cannot load, Aiden automatically restores
`hey_aiden.onnx` with the legacy threshold behavior.
