# Dashboard redesign

The dashboard keeps the existing React 18 / Tailwind 3 stack and REST/WebSocket bridge. Chat and Voice studio share one conversation. PC status and ESP32 controls open from the activity button on desktop and mobile. Settings and history load on demand.

- Text and device microphone requests use `/api/v1/conversation/message`; actions execute on the PC. Typed requests are routed internally as `web_text`, with no speech or desktop overlay. Voice requests retain `web` audio routing.
- Sent messages appear immediately and clear the composer. Client message IDs reconcile HTTP replies and WebSocket broadcasts without duplicate messages. You can draft the next message while waiting.
- Settings → Appearance offers Warm studio, Aiden blue, and Midnight blue. The browser remembers its palette; voice waves, controls, and notifications follow it. Backend settings retain their existing save contract.
- PC & smart home uses live CPU/RAM readings and expandable service details. Fan controls follow the device’s runtime schema, including all timer durations in one selector, with offline blocking and action feedback.
- The favicon and install icons use Aiden’s blue identity.
- Microphone source is explicit. Unsupported device recognition reports an error instead of silently opening the PC microphone.
- Reply audio plays on the browsing device. Replies queue in sequence. Blocked browser autoplay exposes **Play reply**. Muting affects this device only.
- New conversation resets backend context without starting PC capture. Continuing history restores the saved chat context before a follow-up.
- Voice waves illustrate assistant activity; they do not measure audio amplitude. Canvas rendering is capped at 30 fps and 1.5 device pixel ratio, pauses when hidden, and respects reduced motion.
- On a phone, use your existing HTTPS access route to the PC. Browser microphone support and permission are required. HTTP LAN access can still support text, but browsers may block microphone recognition.

## Validation

Run `npm run build` and `CI=true npm run test -- --watchAll=false --runInBand` in `dashboard`. Run `venv/Scripts/python.exe -m pytest tests/test_dashboard_conversation_api.py tests/test_settings_platform.py tests/test_esp32_api.py -q` from the repository root. Run `npm run build:app` in `overlay`.

Desktop and a 390 × 844 mobile viewport were inspected in Chrome, including Settings palettes, Voice studio, and live system/ESP32 status. All 16 dashboard tests and 48 selected backend tests passed, including voice activation and latency regressions. Regression coverage includes immediate chat rendering and deduplication, silent text routing, theme persistence, backend settings saves, exact device targets, failed-message retries, offline blocking, unsupported microphone handling, blocked audio retry, queued playback, muting, and context reset/restoration.

Physical phone microphone/speaker playback and Porcupine/Vosk wake-word capture still need device validation. Restart Aiden to load the updated backend routes, then refresh the dashboard.
