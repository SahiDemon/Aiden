import os
import subprocess
import winreg
from difflib import get_close_matches
import json
import time
import glob
import shutil

# ---------- Helper: locate executable ----------
def find_executable_in_path(app_name):
    for path_dir in os.environ["PATH"].split(os.pathsep):
        exe = os.path.join(path_dir, app_name + ".exe")
        if os.path.exists(exe):
            return exe
    return None


# ---------- Step 1: Built-in Windows apps ----------
def builtin_apps():
    system32 = os.path.join(os.environ["WINDIR"], "System32")
    builtin = {
        "notepad": os.path.join(system32, "notepad.exe"),
        "calc": os.path.join(system32, "calc.exe"),
        "mspaint": os.path.join(system32, "mspaint.exe"),
        "cmd": os.path.join(system32, "cmd.exe"),
        "powershell": os.path.join(system32, "WindowsPowerShell", "v1.0", "powershell.exe"),
    }
    return {k: {"display_name": k.title(), "install_path": os.path.dirname(v), "exe_path": v} for k, v in builtin.items()}


# ---------- Step 2: Registry-based apps ----------
def get_registry_apps():
    apps = {}
    registry_paths = [
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
    ]

    for reg_path in registry_paths:
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path)
            for i in range(winreg.QueryInfoKey(key)[0]):
                try:
                    subkey_name = winreg.EnumKey(key, i)
                    subkey = winreg.OpenKey(key, subkey_name)
                    name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                    path = ""
                    try:
                        path = winreg.QueryValueEx(subkey, "InstallLocation")[0]
                    except FileNotFoundError:
                        pass
                    apps[name.lower()] = {
                        "display_name": name,
                        "install_path": path or "",
                        "exe_path": "",
                    }
                except Exception:
                    continue
        except Exception:
            continue
    return apps


# ---------- Step 3: Start menu shortcuts ----------
def get_startmenu_apps():
    shortcuts = {}
    start_paths = [
        os.path.join(os.environ["PROGRAMDATA"], "Microsoft", "Windows", "Start Menu", "Programs"),
        os.path.join(os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu", "Programs"),
    ]
    for start_path in start_paths:
        for lnk in glob.glob(start_path + "/**/*.lnk", recursive=True):
            name = os.path.splitext(os.path.basename(lnk))[0]
            shortcuts[name.lower()] = {
                "display_name": name,
                "install_path": os.path.dirname(lnk),
                "exe_path": lnk,
            }
    return shortcuts


# ---------- Step 4: Merge all ----------
def build_app_index():
    apps = {}
    apps.update(builtin_apps())
    apps.update(get_registry_apps())
    apps.update(get_startmenu_apps())
    return apps


# ---------- Step 5: Save/load ----------
def cache_apps(apps):
    with open("app_cache.json", "w", encoding="utf-8") as f:
        json.dump(apps, f, indent=2)

def load_cached_apps():
    if os.path.exists("app_cache.json"):
        with open("app_cache.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return None


# ---------- Step 6: Search ----------
def find_app(name, apps):
    name = name.lower()
    matches = get_close_matches(name, list(apps.keys()), n=8, cutoff=0.3)
    if not matches:
        print("❌ No matches found.")
        return None, None

    print("\n🔍 Closest matches:")
    for i, match in enumerate(matches, 1):
        print(f"{i}. {apps[match]['display_name']}")
    choice = input("\nEnter number to launch (or press Enter to cancel): ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(matches):
        key = matches[int(choice) - 1]
        return key, apps[key]
    return None, None


# ---------- Step 7: Launch ----------
def launch_app(app):
    exe = app.get("exe_path")
    name = app["display_name"]

    if exe and os.path.exists(exe):
        print(f"🚀 Launching {name}...\n{exe}")
        os.startfile(exe)
        return

    # Try finding .exe inside install path
    install_path = app.get("install_path", "")
    if install_path and os.path.exists(install_path):
        for root, _, files in os.walk(install_path):
            for f in files:
                if f.lower().endswith(".exe"):
                    exe = os.path.join(root, f)
                    print(f"🚀 Launching {name}...\n{exe}")
                    os.startfile(exe)
                    return

    # Try global PATH
    exe_from_path = find_executable_in_path(name)
    if exe_from_path:
        print(f"🚀 Launching {name}...\n{exe_from_path}")
        os.startfile(exe_from_path)
        return

    print(f"⚠️ Could not launch {name}.")


# ---------- Step 8: Main CLI ----------
def main():
    print("🧠 Windows App Launcher (Fully Fixed)")
    print("------------------------------------")

    apps = load_cached_apps()
    if not apps:
        print("🔍 Scanning all apps... (first run may take 30–60s)")
        apps = build_app_index()
        cache_apps(apps)
        print(f"✅ Indexed {len(apps)} apps.\n")

    while True:
        cmd = input("\nEnter app name ('list' / 'rescan' / 'exit'): ").strip().lower()

        if cmd == "exit":
            print("👋 Bye.")
            break
        elif cmd == "rescan":
            print("🔄 Rebuilding index...")
            apps = build_app_index()
            cache_apps(apps)
            print(f"✅ Indexed {len(apps)} apps.\n")
        elif cmd == "list":
            for i, key in enumerate(sorted(apps.keys()), 1):
                print(f"{i}. {apps[key]['display_name']}")
            print(f"📦 Total: {len(apps)} apps")
        elif cmd:
            match, app = find_app(cmd, apps)
            if match:
                print(f"\n📄 {app['display_name']}")
                print(f"📂 Path: {app['install_path'] or 'N/A'}")
                print(f"⚙️ Executable: {app['exe_path'] or 'Auto-detect'}")
                if input("\nLaunch it? (y/n): ").lower() == "y":
                    launch_app(app)
        else:
            print("⚠️ Invalid input.")


if __name__ == "__main__":
    main()
