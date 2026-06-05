#!/usr/bin/env python3
"""
Append real UPS-style QSvalue lines into the configured ViewPower info.log.

This script ONLY inserts log lines. It does not mock TTS, intercept shutdown,
or call the UPS handler directly.

Quick controls:
- 1: Insert power loss / battery mode
- 2: Insert power restore / AC online
- 3: Insert custom battery event
- 4: Insert custom raw status bits
- p: Print current target path
- q: Quit
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


DEFAULT_INFO_LOG_PATH = r"C:\ViewPower\log\info.log"


def get_info_log_path() -> str:
    env_path = os.getenv("UPS_INFO_LOG_PATH", "").strip()
    if env_path:
        return env_path

    env_file = ROOT_DIR / ".env"
    if env_file.exists():
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip().upper() == "UPS_INFO_LOG_PATH":
                cleaned = value.strip().strip('"').strip("'")
                if cleaned:
                    return cleaned

    return DEFAULT_INFO_LOG_PATH


def build_qs_line(
    *,
    input_voltage: float,
    output_voltage: float,
    load_percentage: int,
    battery_voltage: float,
    status_bits: str,
) -> str:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    cleaned_status = (status_bits.strip() + "00000000")[:8]
    return (
        f"{timestamp} | device:UPS | command:QSvalue("
        f"{input_voltage:.1f} {input_voltage:.1f} {output_voltage:.1f} "
        f"{load_percentage:03d} 50.0 {battery_voltage:.1f} --.- {cleaned_status}"
    )


def append_line(log_path: Path, line: str) -> None:
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()


def prompt_float(label: str, default: float) -> float:
    raw = input(f"{label} [{default}]: ").strip()
    return float(raw) if raw else default


def prompt_int(label: str, default: int) -> int:
    raw = input(f"{label} [{default}]: ").strip()
    return int(raw) if raw else default


def insert_power_loss(log_path: Path) -> None:
    line = build_qs_line(
        input_voltage=238.0,
        output_voltage=238.0,
        load_percentage=30,
        battery_voltage=26.4,
        status_bits="10000000",
    )
    append_line(log_path, line)
    print("[inserted] power loss / battery mode")
    print(line)


def insert_power_restore(log_path: Path) -> None:
    line = build_qs_line(
        input_voltage=238.0,
        output_voltage=238.0,
        load_percentage=30,
        battery_voltage=27.4,
        status_bits="00000000",
    )
    append_line(log_path, line)
    print("[inserted] power restore / AC online")
    print(line)


def insert_custom_battery(log_path: Path) -> None:
    input_voltage = prompt_float("Input voltage", 238.0)
    output_voltage = prompt_float("Output voltage", input_voltage)
    load_percentage = prompt_int("Load percentage", 30)
    battery_voltage = prompt_float("Battery voltage", 26.4)
    line = build_qs_line(
        input_voltage=input_voltage,
        output_voltage=output_voltage,
        load_percentage=load_percentage,
        battery_voltage=battery_voltage,
        status_bits="10000000",
    )
    append_line(log_path, line)
    print("[inserted] custom battery event")
    print(line)


def insert_custom_status_bits(log_path: Path) -> None:
    input_voltage = prompt_float("Input voltage", 238.0)
    output_voltage = prompt_float("Output voltage", input_voltage)
    load_percentage = prompt_int("Load percentage", 30)
    battery_voltage = prompt_float("Battery voltage", 27.4)
    status_bits = input("Raw 8-bit status bits [00000000]: ").strip() or "00000000"
    line = build_qs_line(
        input_voltage=input_voltage,
        output_voltage=output_voltage,
        load_percentage=load_percentage,
        battery_voltage=battery_voltage,
        status_bits=status_bits,
    )
    append_line(log_path, line)
    print("[inserted] custom raw status bits")
    print(line)


def main() -> int:
    log_path = Path(get_info_log_path())
    print(f"Target UPS info log: {log_path}")

    if not log_path.parent.exists():
        print(f"[error] directory does not exist: {log_path.parent}")
        return 1

    if not log_path.exists():
        print("[warn] target log file does not exist yet. It will be created on first insert.")

    while True:
        print("\nChoose an insert:")
        print("  1) Power loss / battery mode")
        print("  2) Power restore / AC online")
        print("  3) Custom battery event")
        print("  4) Custom raw status bits")
        print("  p) Print target path")
        print("  q) Quit")

        choice = input("> ").strip().lower()

        try:
            if choice == "1":
                insert_power_loss(log_path)
            elif choice == "2":
                insert_power_restore(log_path)
            elif choice == "3":
                insert_custom_battery(log_path)
            elif choice == "4":
                insert_custom_status_bits(log_path)
            elif choice == "p":
                print(f"Target UPS info log: {log_path}")
            elif choice == "q":
                print("Exiting.")
                return 0
            else:
                print("Unknown choice.")
        except Exception as exc:
            print(f"[error] {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
