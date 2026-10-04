# Changelog

## Unreleased — 2026-10-04

### Consolidated

- Preserved outstanding branch and worktree changes in main, including microphone readiness/recovery, delayed actions, timer presentation, smart-home controls, and Jellyfin title playback.
- Added independent Jellyfin session recovery and retained runtime prompt overrides while caching prompt defaults.
- Reused normalized Steam manifest fields when matching installed games.

### Improved

- Made the dashboard's System Status shortcut open its panel and labeled the panel toggle for accessibility.
- Replaced outdated onboarding with Windows setup, configuration, architecture, troubleshooting, contribution, and security guides.
- Made setup build the dashboard, reuse the launcher's environment selection, preserve existing configuration, and fail clearly on installation errors.
- Added setup prerequisite checks, developer dependencies, and an optional overlay build without installer packaging.
- Defaulted the API to localhost and left machine-specific optional integrations disabled for new installations.
- Prevented the coordinated release workflow from bundling private configuration, including reused backend output.

### Tidied

- Moved manual, side-effecting diagnostics outside automated test collection; retained regression tests.
- Removed generated Electron output, downloaded Vosk models, optional vendor executables, and machine-specific vendor settings from Git tracking while preserving local files.
- Moved legacy third-party Lego license and changelog files under `tools/licenses` with their attribution intact.

Earlier Aiden changes remain available in Git history. The former root changelog described the third-party Lego tool, not Aiden, and is retained separately.
