"""
List available STT input devices for Aiden.

Useful for finding the correct microphone device index to put into `.env` as
`SPEECH_STT_DEVICE_INDEX`.
"""
from __future__ import annotations

import speech_recognition as sr


def main() -> None:
    try:
        device_names = sr.Microphone.list_microphone_names()
    except Exception as exc:
        print(f"Failed to list microphone devices: {exc}")
        raise SystemExit(1)

    if not device_names:
        print("No microphone devices were found.")
        return

    print("Available STT input devices:\n")
    for index, name in enumerate(device_names):
        print(f"[{index}] {name}")

    print("\nSet the one you want in `.env` like this:")
    print("SPEECH_STT_DEVICE_INDEX=<number>")


if __name__ == "__main__":
    main()
