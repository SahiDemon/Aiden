# Voice and command reliability review

This review strengthens the existing Edge/Groq path without changing the
recognition model, voice, silence threshold, command ordering, or audit commits.
It does not establish that every possible failure is covered.

## Fixed cases

| Case | Behavior after the change | Verification |
| --- | --- | --- |
| Interruption during cache lookup or synthesis | Discard the old reply; allow the next request | Delayed lookup and synthesis tests |
| Interruption while notifications are being sent | Skip stale playback and release browser playback waits | Local and browser queue tests |
| Interrupted synthesis subsequently fails | Skip unnecessary offline generation | Failure after interruption test |
| Online TTS outage | Play offline fallback without storing it as the selected online voice | Network failure test |
| Change voice, pitch, or effective speech rate | Use a distinct cache entry | Edge and Google identity tests |
| Corrupt word timings in Redis | Treat the entry as a miss and regenerate | Invalid JSON, shape, types, and nonfinite timing tests |
| Playback error or cancellation | Stop/unload music and remove the temporary file | Load failure, notification failure, and cancellation tests |
| Malformed command in a batch | Reject that command; continue valid commands | Command validation tests |
| Empty process name or invalid PID | Reject before process discovery or taskkill | Empty-name and invalid-PID tests |
| Redis disconnect yields or fails | Release the registry lock before waiting; continue closing other clients | Shutdown concurrency and failure tests |
| Large streamed speech response | Accumulate bytes with bytearray and convert once | Existing audio/boundary tests and real Edge network smoke check |

The cache namespace changed to include rendered voice settings. Previously
cached phrases regenerate once; old entries expire through the existing TTL.
This temporary cold-cache cost avoids replaying audio with the wrong voice.

## Remaining limits

Gemini latency and remote database latency still vary. There is no evidence
here that changing models, dropping audit writes, or shortening the recording
pause would preserve current accuracy and behavior, so those remain unchanged.

Cancellation invalidates a reply, but a synchronous network request already
running in a worker thread may finish before its resources are released.
Process closing still uses Windows taskkill and its existing success semantics;
this review does not prove all possible permissions, PID races, or app restart
behaviors. Physical microphone/device unplugging, browser autoplay restrictions,
and real acoustic interruption require a manual test after restarting Aiden.

## Research

- [Python task cancellation and worker threads](https://docs.python.org/3.13/library/asyncio-task.html)
- [Python subprocess support and Windows event loops](https://docs.python.org/3/library/asyncio-subprocess.html)
- [SQLAlchemy AsyncSession concurrency](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#using-asyncsession-with-concurrent-tasks)

No dependencies or database schema changes were introduced. Database operations
retain their existing session boundaries and awaited commits.
