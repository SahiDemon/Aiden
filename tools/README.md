# Optional Windows tools

Vendor executables and machine-specific settings are ignored by Git. Existing local copies continue to work; a new clone must provision optional tools separately.

| Tool | Locations checked by Aiden |
| --- | --- |
| NirCmd | `tools/nircmd.exe`, `tools/nircmd/nircmd.exe`, `C:/Tools/nircmd.exe`, `C:/Tools/nircmd/nircmd.exe` |
| ClickMonitorDDC | `tools/ClickMonitorDDC.exe`, `tools/ClickMonitorDDC_7_2.exe`, `tools/ClickMonitorDDC/ClickMonitorDDC.exe`, equivalent `C:/Tools` locations |

Obtain NirCmd from [NirSoft](https://www.nirsoft.net/utils/nircmd.html). Provision ClickMonitorDDC from a trusted publisher source and confirm compatibility with your monitor. These tools enable additional audio/display controls; basic conversation and app launching do not require them.

`spotify_refresh_token_helper.py` assists Spotify credential setup. `generate_cert.py` is a local certificate helper. Review their instructions before using them and keep generated credentials/certificates private.
