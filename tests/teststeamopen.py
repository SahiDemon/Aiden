import re
import sys
from pathlib import Path
import winreg

def get_steam_root():
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam") as k:
            val, _ = winreg.QueryValueEx(k, "InstallPath")
            return Path(val)
    except:
        return None

def parse_libraryfolders(steam_path: Path):
    libs = []
    vdf = steam_path / "steamapps" / "libraryfolders.vdf"
    if not vdf.exists():
        return libs

    text = vdf.read_text(errors="ignore")

    # New style "path" entries
    for m in re.finditer(r'"path"\s+"([^"]+)"', text):
        libs.append(Path(m.group(1)) / "steamapps")

    # Always include main
    main = steam_path / "steamapps"
    if main.exists() and main not in libs:
        libs.insert(0, main)

    return libs

def parse_manifest(manifest: Path):
    text = manifest.read_text(errors="ignore")
    def get(k):
        m = re.search(rf'"{k}"\s+"([^"]+)"', text)
        return m.group(1) if m else None
    return {
        "appid": get("appID") or get("appid"),
        "name": get("name"),
        "installdir": get("installdir")
    }

def find_steam_appid(query: str):
    query_clean = re.sub(r'\W+', '', query.lower())

    steam_root = get_steam_root()
    if not steam_root:
        print("❌ Could not find Steam installation.")
        return None

    libs = parse_libraryfolders(steam_root)

    manifests = []
    for lib in libs:
        for mf in lib.glob("appmanifest_*.acf"):
            info = parse_manifest(mf)
            if info and info["appid"]:
                manifests.append(info)

    # Fuzzy match game names
    for info in manifests:
        name = (info["name"] or "").lower()
        inst = (info["installdir"] or "").lower()
        name_clean = re.sub(r'\W+', '', name)
        inst_clean = re.sub(r'\W+', '', inst)
        if query_clean in name_clean or query_clean in inst_clean:
            return info["appid"], info["name"]

    return None, None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python find_game.py \"cyberpunk\"")
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    appid, name = find_steam_appid(query)

    if appid:
        print(f"✅ Found Game: {name}")
        print(f"🎮 Steam AppID: {appid}")
        print(f"▶ Launch via: steam://run/{appid}")
    else:
        print("❌ Game not found.")
