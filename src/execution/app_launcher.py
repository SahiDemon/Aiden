"""
Dynamic App Launcher
Finds and launches applications without hardcoding - uses intelligent search and caching
"""
import os
import subprocess
import logging
from typing import Optional, List
from pathlib import Path
import winreg
import re

from src.database.redis_client import get_redis_client
from src.utils.logger import get_logger

logger = get_logger(__name__)


class AppLauncher:
    """Dynamically find and launch applications on Windows"""
    
    def __init__(self):
        self.common_search_paths = [
            r"C:\Program Files",
            r"C:\Program Files (x86)",
            os.path.join(os.environ.get("APPDATA", ""), "..\\Local\\Programs"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs"),
            os.environ.get("PROGRAMFILES", ""),
            os.environ.get("PROGRAMFILES(X86)", ""),
        ]
        
        # Common app name mappings for better search
        self.app_aliases = {
            "chrome": [r"C:\Program Files\Google\Chrome\Application\chrome.exe", "chrome.exe", "Google Chrome", "chrome"],
            "chrome.exe": [r"C:\Program Files\Google\Chrome\Application\chrome.exe", "chrome.exe", "Google Chrome", "chrome"],
            "firefox": ["firefox.exe", "Mozilla Firefox", "firefox"],
            "firefox.exe": ["firefox.exe", "Mozilla Firefox", "firefox"],
            "edge": ["msedge.exe", "Microsoft Edge", "edge"],
            "msedge.exe": ["msedge.exe", "Microsoft Edge", "edge"],
            "notepad": ["notepad.exe"],
            "notepad.exe": ["notepad.exe"],
            "vscode": ["Code.exe", "Visual Studio Code", "code"],
            "vs code": ["Code.exe", "Visual Studio Code", "code"],
            "visual studio code": ["Code.exe", "Visual Studio Code"],
            "code": ["Code.exe", "Visual Studio Code"],
            "code.exe": ["Code.exe", "Visual Studio Code"],
            "spotify": ["Spotify.exe"],
            "discord": ["Discord.exe"],
            "calculator": ["calc.exe"],
            "calc": ["calc.exe"],
            "paint": ["mspaint.exe"],
            "explorer": ["explorer.exe"],
            "cmd": ["cmd.exe"],
            "powershell": ["powershell.exe"],
            "terminal": ["wt.exe", "WindowsTerminal.exe"],
            "word": ["WINWORD.EXE", "Microsoft Word"],
            "excel": ["EXCEL.EXE", "Microsoft Excel"],
            "outlook": ["OUTLOOK.EXE", "Microsoft Outlook"],
            "teams": ["Teams.exe", "Microsoft Teams"],
        }
    
    async def launch(self, app_name: str) -> bool:
        """
        Find and launch application
        
        Args:
            app_name: Name of application to launch
            
        Returns:
            True if successfully launched
        """
        app_name_lower = app_name.lower().strip()
        
        try:
            # 1. Try direct path from aliases first (for common apps like Chrome)
            possible_paths = self.app_aliases.get(app_name_lower, [])
            for path in possible_paths:
                if os.path.exists(path) and path.endswith('.exe'):
                    logger.info(f"Launching {app_name} from direct path: {path}")
                    return self._launch_exe(path)
            
            # 2. Use system context to find app (comprehensive registry + start menu scan)
            from src.utils.system_context import get_system_context
            sys_ctx = get_system_context()
            app_info = await sys_ctx.find_app(app_name_lower)
            
            if app_info:
                install_path = app_info.get("install_path", "")
                # Check for Steam appid FIRST if install_path suggests it's a Steam game
                # (Prefer Steam launch even if exe exists, for proper Steam integration)
                if install_path and "steamapps" in install_path.lower():
                    steam_appid = await self._resolve_steam_appid(app_name_lower, install_path)
                    if steam_appid:
                        logger.info(f"Detected Steam game, launching via Steam appid: {steam_appid}")
                        return self._launch_steam_app(steam_appid)
                
                # Try exe_path if available (only if not a Steam game)
                if app_info.get("exe_path") and os.path.exists(app_info["exe_path"]):
                    # Double-check: even if exe_path exists, if it's in a Steam directory, prefer Steam
                    exe_path = app_info["exe_path"]
                    if "steamapps" not in exe_path.lower():
                        logger.info(f"Launching {app_name} from system context: {exe_path}")
                        return self._launch_exe(exe_path)
                
                # Try finding exe in install_path
                if install_path and os.path.exists(install_path):
                    found_exe = self._find_exe_in_directory(install_path)
                    if found_exe:
                        logger.info(f"Found exe in install path: {found_exe}")
                        return self._launch_exe(found_exe)
                    # Final Steam fallback: try launching via Steam appid if no exe found
                    steam_appid = await self._resolve_steam_appid(app_name_lower, install_path)
                    if steam_appid:
                        logger.info(f"Fallback: launching via Steam appid: {steam_appid}")
                        return self._launch_steam_app(steam_appid)
            
            # 3. Try system PATH (but check Steam first if app name suggests Steam game)
            # Before trying PATH, check if this might be a Steam game
            if app_info and app_info.get("install_path"):
                install_path = app_info["install_path"]
                if "steamapps" in install_path.lower():
                    steam_appid = await self._resolve_steam_appid(app_name_lower, install_path)
                    if steam_appid:
                        logger.info(f"Steam game detected before PATH check, launching via Steam: {steam_appid}")
                        return self._launch_steam_app(steam_appid)
            
            # Now try PATH
            if self._try_launch_from_path(app_name_lower):
                return True
            
            # 4. Check Redis cache (legacy)
            redis = await get_redis_client()
            cached_path = await redis.get_app_path(app_name_lower)
            
            if cached_path and os.path.exists(cached_path):
                logger.info(f"Launching {app_name} from cache: {cached_path}")
                return self._launch_exe(cached_path)
            
            # 5. Try Windows Start Menu shortcuts (fallback)
            if await self._launch_from_start_menu(app_name_lower):
                return True
            
            logger.warning(f"Could not find application: {app_name}")
            return False
            
        except Exception as e:
            logger.error(f"Error launching {app_name}: {e}")
            return False
    
    def _find_exe_in_directory(self, directory: str, max_depth: int = 2) -> Optional[str]:
        """Find first .exe file in directory (limited depth for performance)"""
        try:
            for root, dirs, files in os.walk(directory):
                # Limit depth
                depth = root[len(directory):].count(os.sep)
                if depth > max_depth:
                    continue
                
                for file in files:
                    if file.lower().endswith('.exe'):
                        return os.path.join(root, file)
        except Exception as e:
            logger.debug(f"Error searching directory {directory}: {e}")
        
        return None
    
    def _try_launch_from_path(self, app_name: str) -> bool:
        """Try launching app from system PATH"""
        try:
            # Try direct name (suppress output)
            subprocess.Popen(app_name, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info(f"Launched {app_name} from PATH")
            return True
        except:
            pass
        
        # Try with .exe extension
        if not app_name.endswith(".exe"):
            try:
                subprocess.Popen(f"{app_name}.exe", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                logger.info(f"Launched {app_name}.exe from PATH")
                return True
            except:
                pass
        
        return False
    
    async def _find_app_path(self, app_name: str) -> Optional[str]:
        """Search for application executable"""
        # Get possible names
        possible_names = self.app_aliases.get(app_name, [app_name])
        if not app_name.endswith(".exe"):
            possible_names.append(f"{app_name}.exe")
        
        # Search in common locations
        for search_path in self.common_search_paths:
            if not os.path.exists(search_path):
                continue
            
            for possible_name in possible_names:
                # Search recursively (limit depth to 3 for performance)
                found_path = await self._search_directory(
                    search_path,
                    possible_name,
                    max_depth=3
                )
                if found_path:
                    return found_path
        
        return None
    
    async def _search_directory(
        self,
        directory: str,
        target: str,
        max_depth: int = 3,
        current_depth: int = 0
    ) -> Optional[str]:
        """Recursively search directory for executable"""
        if current_depth >= max_depth:
            return None
        
        try:
            for entry in os.scandir(directory):
                try:
                    if entry.is_file():
                        if entry.name.lower() == target.lower():
                            return entry.path
                    elif entry.is_dir() and not entry.name.startswith('.'):
                        result = await self._search_directory(
                            entry.path,
                            target,
                            max_depth,
                            current_depth + 1
                        )
                        if result:
                            return result
                except (PermissionError, OSError):
                    continue
        except (PermissionError, OSError):
            pass
        
        return None
    
    async def _launch_from_start_menu(self, app_name: str) -> bool:
        """Try to launch from Windows Start Menu"""
        try:
            # Common Start Menu locations
            start_menu_paths = [
                os.path.join(os.environ.get("APPDATA", ""), "Microsoft\\Windows\\Start Menu\\Programs"),
                os.path.join(os.environ.get("PROGRAMDATA", ""), "Microsoft\\Windows\\Start Menu\\Programs"),
            ]
            
            for start_path in start_menu_paths:
                if not os.path.exists(start_path):
                    continue
                
                # Search for .lnk files
                for root, dirs, files in os.walk(start_path):
                    for file in files:
                        if file.lower().endswith('.lnk'):
                            if app_name in file.lower():
                                shortcut_path = os.path.join(root, file)
                                logger.info(f"Launching from Start Menu: {shortcut_path}")
                                os.startfile(shortcut_path)
                                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error launching from Start Menu: {e}")
            return False
    
    def _launch_exe(self, path: str) -> bool:
        """Launch executable at given path"""
        try:
            subprocess.Popen(path, shell=True)
            return True
        except Exception as e:
            logger.error(f"Error launching {path}: {e}")
            return False

    async def _resolve_steam_appid(self, app_name_lower: str, install_path: Optional[str]) -> Optional[str]:
        """Resolve Steam appid robustly using registry + libraryfolders + manifests with layered matching."""
        try:
            query = (app_name_lower or "").strip().lower()
            q_norm = re.sub(r"\W+", "", query)

            # Build library list from registry or fallbacks
            libs = self._get_steam_library_steamapps()
            # Add hinted steamapps from install_path
            if install_path and "steamapps" in install_path.lower():
                p = Path(install_path)
                for parent in p.parents:
                    if parent.name.lower() == "steamapps":
                        hinted = str(parent)
                        if hinted not in libs:
                            libs.append(hinted)
                        break
            # Dedupe libs with case-insensitive keys
            libs = list(dict.fromkeys([os.path.normcase(p) for p in libs]))

            # Parse manifests once
            manifests: list[dict] = []
            seen = set()
            for steamapps in libs:
                try:
                    for entry in os.scandir(steamapps):
                        if entry.is_file() and entry.name.startswith("appmanifest_") and entry.name.endswith(".acf"):
                            key = os.path.normcase(entry.path)
                            if key in seen:
                                continue
                            seen.add(key)
                            aid, gname, idir = self._parse_acf_quick(entry.path)
                            if not aid:
                                continue
                            manifests.append({
                                "appid": aid,
                                "name": gname,
                                "installdir": idir,
                                "_manifest": entry.path,
                                "_library": steamapps,
                            })
                except Exception:
                    continue

            # 1) If install_path provided, match by directory name and by steamapps/common path
            if install_path:
                try:
                    ip = Path(install_path)
                    ip_name = ip.name.lower()
                    ip_norm = re.sub(r"\W+", "", ip_name)
                    # exact/fuzzy by installdir
                    for info in manifests:
                        inst = (info.get("installdir") or "").lower()
                        inst_norm = re.sub(r"\W+", "", inst)
                        if inst_norm and (inst_norm == ip_norm or inst_norm in ip_norm or ip_norm in inst_norm):
                            return info["appid"]
                    # check path under steamapps/common
                    if "steamapps" in str(ip).lower():
                        for info in manifests:
                            lib = Path(info["_library"]) if info.get("_library") else None
                            if not lib:
                                continue
                            candidate_folder = lib.parent / "common" / (info.get("installdir") or "")
                            try:
                                if candidate_folder.exists() and str(ip).lower().startswith(str(candidate_folder).lower()):
                                    return info["appid"]
                            except Exception:
                                pass
                except Exception:
                    pass

            # 2) Fuzzy match by installdir or name
            for info in manifests:
                inst = (info.get("installdir") or "").lower()
                name = (info.get("name") or "").lower()
                if not inst and not name:
                    continue
                inst_norm = re.sub(r"\W+", "", inst)
                name_norm = re.sub(r"\W+", "", name)
                if q_norm and (q_norm in inst_norm or q_norm in name_norm or inst_norm in q_norm or name_norm in q_norm):
                    return info["appid"]

            # 3) If the query itself is numeric appid
            if query.isdigit():
                for info in manifests:
                    if info.get("appid") == query:
                        return query

            # 4) Try exe-name heuristic under install_path
            if install_path:
                try:
                    p = Path(install_path)
                    if p.exists():
                        for exe in p.rglob("*.exe"):
                            exe_name = exe.stem.lower()
                            exe_norm = re.sub(r"\W+", "", exe_name)
                            if q_norm in exe_norm or exe_norm in q_norm:
                                for info in manifests:
                                    folder = info.get("installdir") or ""
                                    if folder and folder.lower() in str(p).lower():
                                        return info["appid"]
                except Exception:
                    pass

            return None
        except Exception as e:
            logger.debug(f"Steam appid resolution failed: {e}")
            return None

    def _get_steam_library_steamapps(self) -> List[str]:
        """Return steamapps directories using HKLM + libraryfolders.vdf (mirrors teststeamopen.py approach)."""
        paths: List[str] = []
        steam_root: Optional[str] = None
        # Prefer HKLM WOW6432Node InstallPath (stable for 64-bit Windows)
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\\WOW6432Node\\Valve\\Steam") as k:
                val, _ = winreg.QueryValueEx(k, "InstallPath")
                steam_root = val
        except Exception:
            steam_root = None

        # Fallback defaults if registry missing
        if not steam_root:
            for default in [
                os.path.expandvars(r"C:\\Program Files (x86)\\Steam"),
                os.path.expandvars(r"C:\\Program Files\\Steam"),
                os.path.expandvars(r"C:\\Steam"),
            ]:
                if os.path.isdir(default):
                    steam_root = default
                    break

        if not steam_root:
            return paths

        main_steamapps = os.path.join(steam_root, "steamapps")
        if os.path.isdir(main_steamapps):
            paths.append(main_steamapps)

        # Parse libraryfolders.vdf for additional libraries (new format: "path" entries)
        lib_vdf = os.path.join(main_steamapps, "libraryfolders.vdf")
        try:
            if os.path.isfile(lib_vdf):
                with open(lib_vdf, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
                for m in re.finditer(r'"path"\s+"([^\"]+)"', text):
                    lib_root = m.group(1)
                    steamapps_dir = os.path.join(lib_root, "steamapps")
                    if os.path.isdir(steamapps_dir):
                        paths.append(steamapps_dir)
        except Exception:
            pass

        # Deduplicate preserving order (case-insensitive)
        seen = set()
        unique: List[str] = []
        for p in paths:
            key = os.path.normcase(p)
            if key in seen:
                continue
            seen.add(key)
            unique.append(p)
        return unique

    def _parse_libraryfolders_vdf(self, vdf_path: str) -> List[str]:
        """Parse Steam libraryfolders.vdf to find library paths.
        Supports legacy and new nested formats (entries with a "path" key)."""
        libs: List[str] = []
        try:
            with open(vdf_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = [ln.strip() for ln in f]
            # 1) New format: blocks like: "1" { "path" "D:\\SteamLibrary" ... }
            current_block: dict | None = None
            for ln in lines:
                # Start of a numbered block
                if re.match(r'^"\d+"\s*\{', ln):
                    current_block = {}
                    continue
                # End of block
                if ln == '}' and current_block is not None:
                    p = current_block.get("path")
                    if p and os.path.isdir(p):
                        libs.append(p)
                    current_block = None
                    continue
                if current_block is not None:
                    m = re.search(r'"path"\s*"([^\"]+)"', ln)
                    if m:
                        current_block["path"] = m.group(1)

            # 2) Legacy flat lines: "1"    "D:\\SteamLibrary"
            # Fallback: collect simple key->value with numbers
            for ln in lines:
                m = re.match(r'^"(\d+)"\s*"([^\"]+)"', ln)
                if m:
                    path = m.group(2)
                    if os.path.isdir(path):
                        libs.append(path)
        except Exception:
            pass
        # Deduplicate
        return list(dict.fromkeys(libs))

    def _parse_acf_quick(self, acf_path: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """Quick-parse Steam appmanifest to get (appid, name, installdir)."""
        appid = None
        name = None
        installdir = None
        try:
            with open(acf_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line_l = line.strip()
                    if not appid:
                        # accept both "appid" and "appID" keys (case-insensitive)
                        m = re.search(r'"app[idID]{2}"\s*"(\d+)"', line_l, flags=re.IGNORECASE)
                        if m:
                            appid = m.group(1)
                            continue
                    if not name:
                        m = re.search(r'"name"\s*"([^\"]+)"', line_l, flags=re.IGNORECASE)
                        if m:
                            name = m.group(1)
                            continue
                    if not installdir:
                        m = re.search(r'"installdir"\s*"([^\"]+)"', line_l, flags=re.IGNORECASE)
                        if m:
                            installdir = m.group(1)
                            continue
                    if appid and name and installdir:
                        break
        except Exception:
            pass
        return appid, name, installdir

    def _launch_steam_app(self, appid: str) -> bool:
        """Launch a Steam game by appid using steam protocol (steam://run/<id>) or steam.exe -applaunch."""
        try:
            # Preferred: protocol (use steam://run/<id> for compatibility)
            subprocess.Popen(f'start "" "steam://run/{appid}"', shell=True)
            logger.info(f"Launching Steam appid via protocol (run): {appid}")
            return True
        except Exception:
            # Fallback: steam.exe -applaunch
            for steamapps in self._get_steam_library_steamapps():
                steam_dir = os.path.dirname(steamapps)
                steam_exe = os.path.join(steam_dir, "steam.exe")
                if os.path.isfile(steam_exe):
                    try:
                        subprocess.Popen(f'"{steam_exe}" -applaunch {appid}', shell=True)
                        logger.info(f"Launching Steam appid via steam.exe -applaunch: {appid}")
                        return True
                    except Exception:
                        continue
        logger.warning(f"Failed to launch Steam appid: {appid}")
        return False

    def _find_steam_candidates(self, name_hint: str, install_path: Optional[str] = None) -> List[dict]:
        """Return a list of candidate Steam manifests matching name/installdir (for debugging).
        Also scans the steamapps folder inferred from install_path if provided.
        """
        candidates: List[dict] = []
        try:
            libs = self._get_steam_library_steamapps()
            # Add hinted steamapps from install_path if available
            if install_path and "steamapps" in install_path.lower():
                p = Path(install_path)
                for parent in p.parents:
                    if parent.name.lower() == "steamapps":
                        hinted = str(parent)
                        if hinted not in libs:
                            libs.append(hinted)
                        break
            name_norm = (name_hint or "").lower()
            for steamapps in libs:
                try:
                    for entry in os.scandir(steamapps):
                        if entry.is_file() and entry.name.startswith("appmanifest_") and entry.name.endswith(".acf"):
                            aid, gname, idir = self._parse_acf_quick(entry.path)
                            if not aid:
                                continue
                            gname_l = (gname or "").lower()
                            idir_l = (idir or "").lower()
                            if name_norm and (name_norm in gname_l or name_norm in idir_l):
                                candidates.append({
                                    "appid": aid,
                                    "name": gname,
                                    "installdir": idir,
                                    "steamapps": steamapps,
                                    "manifest": entry.path,
                                })
                except Exception:
                    continue
        except Exception:
            pass
        return candidates


# Global instance
_app_launcher: Optional[AppLauncher] = None


def get_app_launcher() -> AppLauncher:
    """Get or create global app launcher"""
    global _app_launcher
    if _app_launcher is None:
        _app_launcher = AppLauncher()
    return _app_launcher



