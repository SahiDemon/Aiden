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
`./run_kitten_experiment.ps1 -Baseline` for the Edge/Groq comparison. Keep the
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
