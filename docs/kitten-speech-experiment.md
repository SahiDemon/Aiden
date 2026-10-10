# Kitten speech experiment

Branch: `codex/kitten-speech-experiment`. The pre-experiment changes were
committed and pushed to `main` as `0f5c14f`.

This integration uses the **hosted API** matching the playground: Kitten TTS 2,
Eleanor (`eleanor_somber_female_32`), and Kitten-ASR Pro Enhanced
(`kittenasr-enhanced-preview`). It does not download or run speech model weights
locally. The local GitHub TTS package has a different streaming implementation;
the playground's ASR service is separate from that package.

## Run the comparison

The Kitten key belongs only in the ignored `.env`:

```dotenv
SPEECH_KITTEN_API_KEY=<YOUR_KEY>
```

Close the existing tray instance before starting a different provider. From a
PowerShell terminal at the repository root:

```powershell
# Eleanor streaming TTS + realtime Kitten STT
.\run_kitten_experiment.ps1

# Edge TTS + Groq Whisper with Vosk live captions
.\run_kitten_experiment.ps1 -Baseline
```

The launcher chooses providers for its child process; ordinary `run_aiden.ps1`
launches retain the `.env` defaults. `SPEECH_KITTEN_EXPERIMENT=true` makes these
process selectors override saved dashboard provider preferences. Keys never
enter frontend payloads or Git. Requests use hosted services and consume account
quota; both microphone audio and reply text are sent to KittenML when selected.

The realtime WebSocket opens for each microphone capture, concurrently with
capture setup. It sends 200ms PCM appends from the existing 16kHz VAD capture,
replaces live captions with each partial snapshot, commits when local VAD ends
the turn, and accepts only the final plain transcript for command execution.
This retains Aiden's cue suppression, media ducking, minimum speech gates, and
noise rejection. It does not reduce the existing VAD end-of-speech delay.

Buffered commands captured by the wake-word detector use Kitten's upload ASR.
Desktop TTS consumes progressive 24kHz PCM with a 350ms initial playback buffer,
then writes arriving audio to the output stream. Barge-in aborts that stream.
Browser-origin TTS uses a complete WAV through the existing browser playback
queue. Browser microphone recognition remains the browser's existing speech
recognition path. Desktop streaming audio is not mirrored to browser clients;
caption/progress messages are still broadcast. No browser UI changes were made.

## Configuration and failure behavior

All fields are validated by `SpeechConfig`, with `SPEECH_` prefixes:

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `SPEECH_TTS_PROVIDER` | `edge` | Select `kitten` for the experiment |
| `SPEECH_STT_PROVIDER` | `groq` | Select `kitten` for capture and buffered commands |
| `SPEECH_KITTEN_TTS_MODEL` | `kitten-tts-2-latest` | Hosted speech model |
| `SPEECH_KITTEN_TTS_VOICE` | `eleanor_somber_female_32` | Eleanor voice |
| `SPEECH_KITTEN_TTS_SPEED` | `1.0` | 0.25–4.0 speech speed |
| `SPEECH_KITTEN_STT_MODEL` | `kittenasr-enhanced-preview` | Hosted recognizer |
| `SPEECH_KITTEN_STT_DELAY` | `minimal` | Target partial cadence; minimal targets 500ms |
| `SPEECH_KITTEN_TIMEOUT` | `30` | 5–120s request/inactivity or final-result timeout |
| `SPEECH_KITTEN_FALLBACK` | `true` | Groq on ASR error; Edge before desktop TTS starts |
| `SPEECH_KITTEN_EXPERIMENT` | `false` | Launcher provider precedence |

Fallback is logged and must not be counted as a successful Kitten result.
Desktop playback never restarts a partially spoken reply after a stream fails.
Browser full-file generation retains the existing offline TTS fallback when
fallback is enabled. Incomplete SSE audio and realtime sessions without a final
transcript are errors. Bounded audio queues protect microphone capture from a
slow connection. Set `SPEECH_KITTEN_FALLBACK=false` to expose failures while
evaluating Kitten itself.

## Automated benchmark

```powershell
.venv\Scripts\python.exe tools\benchmark_kitten_speech.py --repeats 3

# Same real recording sent to both ASR providers; does not execute the transcript
.venv\Scripts\python.exe tools\benchmark_kitten_speech.py --repeats 3 `
  --audio .local\kitten-speech\my-command.wav --expected "Open Chrome"
```

Generated comparison audio and raw JSON are saved in ignored
`.local/kitten-speech/`. Benchmarks bypass caches and fallback. TTS order
alternates per trial. ASR uses the same mono 16kHz recording; realtime audio is
paced to its actual duration. `after_capture_s` measures the wait after audio is
available (uploads) or after the last paced append (realtime). The replay includes
session setup during playback, as the integration does during capture setup.
It excludes microphone startup, VAD endpoint delay, LLM time, command execution,
and audio device startup.

### Initial measurements — 11 October 2026

Three texts, three trials each for TTS; one synthetic 2.89s Eleanor command,
three trials for each ASR path. This is a small smoke comparison, not an accent,
noise, or conversational accuracy evaluation.

| Measurement | Baseline median | Kitten median |
| --- | ---: | ---: |
| Reply audio ready to play | Edge: 0.842s | Streaming PCM + 350ms buffer: 1.195s |
| Final recognition wait after capture | Groq: 0.572s | Realtime: 2.144s |
| Final recognition wait after capture | Groq: 0.572s | Upload: 2.429s |

Both ASR providers returned the reference command without word errors across
these synthetic trials. First realtime partial text arrived at 2.45–2.68s from
the start of the paced 2.89s recording. Actual desktop streaming playback also
succeeded, with the first playback starting at 1.241s in a separate smoke test.

**Finding:** Kitten works, but these measurements favor the current Edge/Groq
stack for latency. Keep Kitten optional if Eleanor's sound or expression is
preferred. A natural microphone comparison is still needed before judging
recognition accuracy or adopting it as the default.

## Manual acceptance checks

1. Test each launcher with the same microphone, distance, and background noise.
2. Say "Open Chrome", "Open Discord", and "Play something on Spotify and turn
   off the fan"; confirm captions revise while speaking and commands execute once
   after final recognition. Use the combined command only when controlling your
   fan is intended.
3. Test short pauses, quiet speech, and interruption while Eleanor speaks.
4. Verify wake readiness, media pause/restore, and wake detection after playback.
5. Repeat with several real recordings using `--audio` and reference transcripts.
6. Compare perceived voice quality separately from first-audio and final-ASR
   latency. A faster partial caption is not proof of faster command execution.

## Protocol sources

- [Kitten output streaming](https://docs.kittenml.com/tts/stream-output)
- [Kitten realtime transcription](https://docs.kittenml.com/stt/realtime)
- [Realtime event fields](https://docs.kittenml.com/stt/realtime-events)
- [Upload transcription](https://docs.kittenml.com/stt/upload-transcription)
- [Local TTS project](https://github.com/KittenML/KittenTTS)
