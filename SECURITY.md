# Security and privacy

Aiden can launch/close programs, control media, issue Windows actions, and execute shell commands with your user’s permissions. Treat access to its backend as access to those capabilities.

## Local and remote access

Keep `API_HOST=localhost`, the shipped default. The backend does not independently authenticate its command/API callers. Local software running as your user can reach the local API. Do not publish it through port forwarding or a tunnel without an authentication boundary.

For Cloudflare Tunnel, configure a Cloudflare Access application that allows only intended identities, require MFA, avoid broad bypass policies, and enable Access token validation at the tunnel/origin. Verify anonymous requests are rejected for REST and WebSocket endpoints. A login screen alone does not prove alternate routes are protected.

Cloudflare account MFA protects the administrative account; Access MFA protects the published application and has separate enrollment. A longer Access session reduces repeat logins but increases the period in which a stolen session could remain useful. Keep devices locked and revoke sessions when a device or account is compromised.

## Credentials and release output

- Store secrets only in local `.env` or appropriate environment variables; commit placeholders in `.env.example`.
- Do not commit tunnel tokens, service-account JSON, personal wake models, transcripts, or diagnostic recordings.
- `scripts/release/build_release.ps1` writes a blank configuration template into the packaged backend, including reused build output.
- `scripts/release/build_exe.ps1` is intended for a personal executable and can copy the local `.env`; do not redistribute it without sanitizing configuration.
- Review `dist/Aiden`, Electron extra resources, and optional tools before publishing artifacts. Ignoring files in Git does not automatically exclude them from packaging.

## Data flow

Wake-word recognition is local. Recorded voice commands are sent to Groq for transcription. Selected cloud LLM providers receive conversation/context data, which can include application and process information. Edge TTS and Google TTS use network services. Ollama moves LLM inference to your configured endpoint, but does not replace Groq voice transcription or the configured database/cache.

PostgreSQL and Redis store application data. Logs and explicitly enabled diagnostics may contain private text or audio. Redact logs before sharing, configure retention appropriate to your use, and back up credentials securely outside the repository.

## Report an issue

Report security issues privately to the repository owner through your established contact channel. Provide the affected version and reproduction steps without publishing credentials or an exploit against a live installation. Rotate exposed credentials promptly; deleting a committed file does not remove it from Git history.
