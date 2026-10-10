# Baseline voice latency

Keep Edge TTS and Groq STT as the baseline. The captured baseline logs showed
Groq transcription taking 258–261 ms, while the combined AI and speech queue
stage took 7.38–10.93 seconds. Recording time includes the spoken command and
the silence used to decide that speech has finished.

Generated speech now enters the playback queue before Redis persists the audio
and word timings. Persistence remains awaited, and playback uses word timings
already held in memory. A synthetic diagnostic measured Redis audio and timing
writes at 495 ms on the first call and approximately 80 ms on two subsequent
calls. These writes can now overlap playback; this is not a measured reduction
in total conversational latency.

Restart the assistant to load the changes, then use
`./run_aiden.ps1 -Debug` for the Edge/Groq comparison. Keep the
same microphone and repeat the same commands a few times. The debug logs now
separate these stages:

- Context and AI planning, including Gemini request time.
- Each command action and its command history save.
- TTS cache lookup, generation, cache save, and first local playback.
- Conversation context save.

First local playback measures elapsed time from the TTS request to starting the
pygame mixer. It includes queue waits; it does not measure the hardware's audible
output latency. Browser playback acknowledgements follow the existing path.

Command ordering, audit persistence, recognition providers, and the silence
threshold are unchanged. Investigate the slow stage from the new logs before
changing those behaviors. In the supplied example, "open crook" meant Chrome;
Gemini's interpretation was correct.

## Follow-up microphone run

The next captured run identified substantial command-side delays:

| Stage | Close Chrome + fan off | Fan on + Notepad |
| --- | ---: | ---: |
| Final transcription | 259 ms | 240 ms |
| Gemini generation | 1,600 ms | 6,878 ms |
| Command actions | 14,755 ms | 209 ms |
| Command history saves | 6,606 ms | 3,978 ms |
| TTS request to local playback | 1,238 ms | 1,201 ms |

Chrome closing invoked taskkill sequentially for 34 selected processes. PID
closing now runs off the event loop with at most eight concurrent calls and
awaits every selected target before returning. The next top-level command still
executes in order. Spotify retains its existing close-and-verify behavior.

Command history no longer refreshes the just-inserted row: the insert already
populates its ID and timestamp. Commit remains awaited. A real database
diagnostic verified ID, timestamp, and serialization before rollback; the
redundant refresh alone took 472 ms in that trial. Database writes still incur
network latency, and Gemini response time varies. Further microphone runs are
needed to measure the combined improvement.
