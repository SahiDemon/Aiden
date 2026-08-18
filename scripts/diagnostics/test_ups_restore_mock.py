#!/usr/bin/env python3
"""
Mock the UPS power-loss and power-restore flow without touching the real UPS.

Scenarios:
- Default: AC online -> power loss -> power restored
- Confirm shutdown: AC online -> power loss -> user confirms shutdown -> power restored

This script uses the real UPS monitor and UPS handler logic, but replaces:
- TTS output with console prints
- context injection with console prints
- Windows shutdown/shutdown-abort commands with a fake in-memory simulator
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
import time
import types
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace


ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


@dataclass
class FakeShutdownState:
    shutdown_started: bool = False
    abort_attempted: bool = False
    abort_succeeded: bool = False
    no_shutdown_in_progress: bool = False
    shutdown_commands: int = 0

    def run(self, command: list[str], capture_output: bool = False, text: bool = False, check: bool = False):
        joined = " ".join(command)
        print(f"[mock subprocess] {joined}")

        if command[:2] == ["shutdown", "/a"]:
            self.abort_attempted = True
            if self.shutdown_started:
                self.shutdown_started = False
                self.abort_succeeded = True
                return SimpleNamespace(returncode=0, stdout="Shutdown aborted.", stderr="")

            self.no_shutdown_in_progress = True
            return SimpleNamespace(
                returncode=1116,
                stdout="",
                stderr="No shutdown was in progress."
            )

        if len(command) >= 2 and command[0] == "shutdown" and command[1] == "/s":
            self.shutdown_started = True
            self.shutdown_commands += 1
            return SimpleNamespace(returncode=0, stdout="Shutdown scheduled.", stderr="")

        return SimpleNamespace(returncode=0, stdout="", stderr="")


class FakeTTS:
    async def play_sound(self, sound_name: str):
        print(f"[fake tts] sound: {sound_name}")

    async def speak(self, text: str):
        print(f"[fake tts] speak: {text}")


class FakeContextManager:
    async def inject_assistant_message(self, message: str, expecting_followup: bool = False):
        print(f"[fake context] inject: expecting_followup={expecting_followup} | {message}")


def install_fake_context_manager():
    fake_module = types.ModuleType("src.core.context_manager")
    fake_module.get_context_manager = lambda: FakeContextManager()
    sys.modules["src.core.context_manager"] = fake_module


def make_test_handler():
    from src.utils.ups_handler import UPSEventHandler

    handler = object.__new__(UPSEventHandler)
    handler.settings = None
    handler.tts = FakeTTS()
    handler.shutdown_task = None
    handler.waiting_for_response = False

    async def fake_auto_listen():
        print("[fake assistant] auto-listen triggered")

    handler._trigger_auto_listen = fake_auto_listen
    return handler


def build_qs_line(on_battery: bool, battery_voltage: float = 27.2, load: int = 30, input_voltage: float = 238.0) -> str:
    status_bits = "10000000" if on_battery else "00000000"
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    return (
        f"{timestamp} | device:UPS | command:QSvalue("
        f"{input_voltage:.1f} {input_voltage:.1f} {input_voltage:.1f} {load:03d} 50.0 {battery_voltage:.1f} --.- {status_bits}\n"
    )


def append_log_line(log_path: Path, line: str):
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()


async def run_scenario(confirm_shutdown: bool, restore_wait: float):
    install_fake_context_manager()

    import src.utils.ups_handler as ups_handler_module
    from src.utils.ups_monitor import UPSMonitor

    shutdown_state = FakeShutdownState()
    original_run = ups_handler_module.subprocess.run
    ups_handler_module.subprocess.run = shutdown_state.run

    temp_dir = Path(tempfile.mkdtemp(prefix="aiden-ups-mock-"))
    log_path = temp_dir / "info.log"
    log_path.write_text("", encoding="utf-8")

    print(f"[mock] using temporary log: {log_path}")

    handler = make_test_handler()
    loop = asyncio.get_running_loop()
    monitor = UPSMonitor(
        info_log_path=str(log_path),
        polling_interval=0.1,
        on_power_lost=handler.handle_power_lost,
        on_power_restored=handler.handle_power_restored,
        on_battery_alert=handler.handle_battery_alert,
        on_battery_critical=handler.handle_battery_critical,
        on_shutdown_request=handler.handle_shutdown_request,
        main_event_loop=loop,
    )

    try:
        monitor.start()

        print("[mock] establish baseline: AC online")
        append_log_line(log_path, build_qs_line(on_battery=False))
        await asyncio.sleep(0.5)

        print("[mock] simulate power loss")
        append_log_line(log_path, build_qs_line(on_battery=True, battery_voltage=26.4))
        await asyncio.sleep(1.0)

        if confirm_shutdown:
            print("[mock] simulate user confirming shutdown")
            handler.user_confirmed_shutdown(True)
            await asyncio.sleep(2.0)
        else:
            print("[mock] no shutdown confirmation sent")
            await asyncio.sleep(restore_wait)

        print("[mock] simulate power restore")
        append_log_line(log_path, build_qs_line(on_battery=False, battery_voltage=27.4))
        await asyncio.sleep(1.5)

    finally:
        monitor.stop()
        ups_handler_module.subprocess.run = original_run

    print("\n=== Mock Summary ===")
    print(f"waiting_for_response: {handler.waiting_for_response}")
    print(f"shutdown_started: {shutdown_state.shutdown_started}")
    print(f"shutdown_commands: {shutdown_state.shutdown_commands}")
    print(f"abort_attempted: {shutdown_state.abort_attempted}")
    print(f"abort_succeeded: {shutdown_state.abort_succeeded}")
    print(f"no_shutdown_in_progress: {shutdown_state.no_shutdown_in_progress}")
    print(f"monitor_mode: {monitor.current_mode.value}")

    if confirm_shutdown:
        success = (
            shutdown_state.shutdown_commands >= 1
            and shutdown_state.abort_attempted
            and shutdown_state.abort_succeeded
            and not handler.waiting_for_response
            and monitor.current_mode.value == "ac_online"
        )
    else:
        success = (
            shutdown_state.shutdown_commands == 0
            and shutdown_state.abort_attempted
            and shutdown_state.no_shutdown_in_progress
            and not handler.waiting_for_response
            and monitor.current_mode.value == "ac_online"
        )

    print(f"result: {'PASS' if success else 'FAIL'}")
    return 0 if success else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mock UPS power-loss/power-restore flow.")
    parser.add_argument(
        "--confirm-shutdown",
        action="store_true",
        help="Simulate the user confirming shutdown before power is restored.",
    )
    parser.add_argument(
        "--restore-wait",
        type=float,
        default=1.0,
        help="Seconds to wait before simulating power restore in the non-confirmation scenario.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return asyncio.run(
        run_scenario(
            confirm_shutdown=args.confirm_shutdown,
            restore_wait=args.restore_wait,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
