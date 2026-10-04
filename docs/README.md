# Aiden documentation

Start with [Windows setup](setup.md), then use [configuration](configuration.md) to enable the integrations you own.

| Guide | Use it for |
| --- | --- |
| [Setup](setup.md) | Prerequisites, installation, first launch, and updates |
| [Configuration](configuration.md) | Required services, microphones, LLMs, and optional hardware |
| [Troubleshooting](troubleshooting.md) | Startup, audio, dashboard, and service connection problems |
| [Architecture](architecture.md) | Assistant flow, module boundaries, persistence, and UI events |
| [Design](design.md) | Dashboard tone, timers, and visual consistency |
| [Contributing](../CONTRIBUTING.md) | Development commands, checks, and PR expectations |
| [Security](../SECURITY.md) | Credential handling and remote access |

## Integration guides

- [Google Chirp TTS](guides/google-chirp-tts.md)
- [UPS monitoring](guides/ups-monitoring.md) — review the shutdown behavior before enabling
- [Personalized wake-word detection](guides/wake-word/personalized-v2.md)
- [Wake-word debugging](guides/wake-word/debugging.md)
- [Wake-word diagnostic toolkit](guides/wake-word/solution-summary.md)
- [Dashboard development](../dashboard/README.md)
- [Overlay development](../overlay/README.md)

The wake-word guides describe specialized tuning workflows. Start with the default Vosk setup before collecting audio or training a custom model. Local model paths, thresholds, hardware addresses, and credentials are specific to each installation.
