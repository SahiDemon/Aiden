"""
System Context Provider
Provides AI with information about installed apps and running processes
"""
import os
import re
import winreg
import glob
import psutil
import json
import logging
from itertools import islice
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from difflib import get_close_matches

from src.database.redis_client import get_redis_client
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SystemContextProvider:
    """Provides system context (apps, processes) to AI for better decision making"""
    
    CACHE_FILE = str(Path(__file__).resolve().parent.parent / "temp" / "system_context_cache.json")
    CACHE_TTL = 3600  # 1 hour in seconds
    
    def __init__(self):
        self.installed_apps_cache: Optional[Dict[str, Any]] = None
        self.running_processes_cache: Optional[List[Dict[str, Any]]] = None
    
    async def get_installed_apps(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Get all installed applications with paths
        
        Args:
            force_refresh: Force rescan instead of using cache
            
        Returns:
            Dictionary of app_name -> {display_name, install_path, exe_path}
        """
        # Try Redis cache first
        if not force_refresh:
            try:
                redis = await get_redis_client()
                cached = await redis.get("system:installed_apps")
                if cached:
                    logger.debug("Using cached installed apps from Redis")
                    return json.loads(cached)
            except Exception as e:
                logger.debug(f"Redis cache miss for installed apps: {e}")
        
        # Try file cache
        if not force_refresh and os.path.exists(self.CACHE_FILE):
            try:
                import time
                cache_age = time.time() - os.path.getmtime(self.CACHE_FILE)
                if cache_age < self.CACHE_TTL:
                    with open(self.CACHE_FILE, 'r', encoding='utf-8') as f:
                        cached_data = json.load(f)
                        logger.debug("Using cached installed apps from file")
                        # Save to Redis too
                        try:
                            redis = await get_redis_client()
                            await redis.set("system:installed_apps", json.dumps(cached_data), ex=self.CACHE_TTL)
                        except Exception:
                            pass
                        return cached_data
            except Exception as e:
                logger.debug(f"File cache read failed: {e}")
        
        # Perform scan
        logger.info("Scanning installed applications...")
        apps = {}
        
        # 1. Built-in Windows apps
        apps.update(self._get_builtin_apps())
        
        import asyncio
        # 2. Registry-based apps (run in thread to prevent blocking event loop)
        apps.update(await asyncio.to_thread(self._get_registry_apps))
        
        # 3. Start menu shortcuts (run in thread to prevent blocking event loop)
        apps.update(await asyncio.to_thread(self._get_startmenu_apps))
        
        logger.info(f"Found {len(apps)} installed applications")
        
        # Cache results
        try:
            os.makedirs(os.path.dirname(self.CACHE_FILE), exist_ok=True)
            with open(self.CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(apps, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to write app cache file: {e}")
        
        # Cache in Redis
        try:
            redis = await get_redis_client()
            await redis.set("system:installed_apps", json.dumps(apps), ex=self.CACHE_TTL)
        except Exception as e:
            logger.debug(f"Failed to cache apps in Redis: {e}")
        
        return apps
    
    def _get_builtin_apps(self) -> Dict[str, Any]:
        """Get built-in Windows applications"""
        system32 = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "System32")
        builtin = {
            "notepad": os.path.join(system32, "notepad.exe"),
            "calc": os.path.join(system32, "calc.exe"),
            "mspaint": os.path.join(system32, "mspaint.exe"),
            "cmd": os.path.join(system32, "cmd.exe"),
            "powershell": os.path.join(system32, "WindowsPowerShell", "v1.0", "powershell.exe"),
            "explorer": os.path.join(system32, "explorer.exe"),
            "magnify": os.path.join(system32, "Magnify.exe"),
        }
        
        result = {}
        for key, path in builtin.items():
            if os.path.exists(path):
                result[key] = {
                    "display_name": key.title(),
                    "install_path": os.path.dirname(path),
                    "exe_path": path
                }
        
        return result
    
    def _get_registry_apps(self) -> Dict[str, Any]:
        """Scan Windows Registry for installed applications"""
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
                        
                        try:
                            name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                        except FileNotFoundError:
                            continue
                        
                        install_path = ""
                        exe_path = ""
                        
                        # Try InstallLocation
                        try:
                            install_path = winreg.QueryValueEx(subkey, "InstallLocation")[0]
                        except FileNotFoundError:
                            pass
                        
                        # Try DisplayIcon (often points to exe)
                        try:
                            icon = winreg.QueryValueEx(subkey, "DisplayIcon")[0]
                            if icon and icon.lower().endswith('.exe'):
                                exe_path = icon.strip('"')
                            elif icon and ',' in icon:
                                exe_path = icon.split(',')[0].strip('"')
                        except FileNotFoundError:
                            pass
                        
                        if name:
                            apps[name.lower()] = {
                                "display_name": name,
                                "install_path": install_path or "",
                                "exe_path": exe_path or "",
                            }
                        
                    except Exception:
                        continue
                        
            except Exception:
                continue
        
        return apps
    
    def _get_startmenu_apps(self) -> Dict[str, Any]:
        """Scan Windows Start Menu for application shortcuts"""
        shortcuts = {}
        start_paths = [
            os.path.join(os.environ.get("PROGRAMDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs"),
            os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs"),
        ]
        
        for start_path in start_paths:
            if not os.path.exists(start_path):
                continue
            
            try:
                for lnk in glob.glob(os.path.join(start_path, "**", "*.lnk"), recursive=True):
                    name = os.path.splitext(os.path.basename(lnk))[0]
                    shortcuts[name.lower()] = {
                        "display_name": name,
                        "install_path": os.path.dirname(lnk),
                        "exe_path": lnk,
                    }
            except Exception as e:
                logger.debug(f"Error scanning Start Menu path {start_path}: {e}")
                continue
        
        return shortcuts
    
    async def get_running_processes(self, simplified: bool = True) -> List[Dict[str, Any]]:
        """
        Get list of currently running processes
        
        Args:
            simplified: If True, return simplified list for AI context (excludes system processes)
            
        Returns:
            List of process dictionaries
        """
        processes = []
        
        # Extended list of system/background processes to exclude from AI context
        system_processes = {
            'system', 'registry', 'smss.exe', 'csrss.exe', 'wininit.exe',
            'services.exe', 'lsass.exe', 'svchost.exe', 'dwm.exe', 'winlogon.exe',
            'fontdrvhost.exe', 'lsaiso.exe', 'memcompression', 'runtimebroker.exe',
            'sihost.exe', 'taskhostw.exe', 'searchindexer.exe', 'searchhost.exe',
            'startmenuexperiencehost.exe', 'shellexperiencehost.exe', 'textinputhost.exe',
            'conhost.exe', 'spoolsv.exe', 'dashost.exe', 'securityhealthservice.exe',
            'securityhealthsystray.exe', 'mpcmdrun.exe', 'nissrv.exe', 'msmpseng.exe',
            'mpdefendercoreservice.exe', 'msmpeng.exe',  # Windows Defender
            'wuauclt.exe', 'trustedinstaller.exe', 'tiworker.exe',  # Windows Update
            'vmmem',  # WSL memory
        }
        
        try:
            for proc in psutil.process_iter(['pid', 'name', 'exe', 'status', 'cpu_percent', 'memory_percent']):
                try:
                    info = proc.info
                    
                    if simplified:
                        # Only include user-relevant processes (skip system processes)
                        name = info.get('name', '').lower()
                        if name in system_processes:
                            continue
                        
                        processes.append({
                            "name": info.get('name', 'Unknown'),
                            "pid": info.get('pid'),
                            "status": info.get('status', 'unknown'),
                            "exe": info.get('exe') or "",
                            "memory_percent": round(float(info.get('memory_percent') or 0), 2),
                        })
                    else:
                        processes.append({
                            "pid": info.get('pid'),
                            "name": info.get('name', 'Unknown'),
                            "path": info.get('exe', 'N/A'),
                            "status": info.get('status', 'unknown'),
                            "cpu_percent": round(info.get('cpu_percent', 0), 2),
                            "memory_percent": round(info.get('memory_percent', 0), 2)
                        })
                
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        
        except Exception as e:
            logger.error(f"Error getting running processes: {e}")
        
        return processes
    
    async def get_ai_context(self) -> Dict[str, Any]:
        """
        Get system context formatted for AI
        Returns minimal, relevant information to help AI make decisions
        
        Returns:
            Dictionary with installed_apps and running_processes
        """
        try:
            # Get installed apps (from cache)
            apps = await self.get_installed_apps()
            
            # Get running processes (simplified)
            processes = await self.get_running_processes(simplified=True)
            
            # Format for AI - provide app names WITH paths for better context
            app_list = []
            for key, app in islice(sorted(apps.items(), key=lambda x: x[1]['display_name'].lower()), 80):
                name = app["display_name"]
                exe_path = app.get("exe_path", "")
                install_path = app.get("install_path", "")
                
                # Include path if available (prefer exe_path)
                if exe_path:
                    app_list.append(f"{name} ({exe_path})")
                elif install_path:
                    app_list.append(f"{name} ({install_path})")
                else:
                    app_list.append(name)
            
            # Prioritize common user apps with category annotations (one row per PID so kill is unambiguous)
            category_map = [
                (['chrome', 'firefox', 'msedge', 'brave', 'opera'], '[browser]'),
                (['spotify', 'itunes', 'musicbee', 'foobar', 'vlc', 'aimp', 'winamp'], '[media/music]'),
                (['discord', 'teams', 'slack', 'zoom', 'skype', 'telegram', 'whatsapp'], '[communication]'),
                (['vscode', 'code', 'pycharm', 'cursor', 'sublime', 'atom', 'brackets', 'notepad', 'studio'], '[editor]'),
                (['python', 'node', 'java', 'dotnet', 'powershell', 'cmd', 'postman', 'docker', 'git'], '[dev-tool]'),
                (['obs', 'streamlabs'], '[recording]'),
                (['steam', 'epic', 'origin', 'uplay', 'battle', 'gog', 'playnite'], '[game-launcher]'),
                (['warframe', 'minecraft', 'fortnite', 'valorant', 'csgo', 'dota', 'overwatch', 'roblox', 'genshin', 'league', 'apex', 'tf2', 'rust', 'pubg', 'rocket', 'destiny'], '[game]'),
                (['nvidia', 'radeon', 'afterburner', 'rtss'], '[gpu-tool]'),
                (['excel', 'word', 'outlook', 'powerpoint', 'onenote'], '[office]'),
                (['premiere', 'photoshop', 'illustrator', 'aftereffects', 'lightroom', 'audition'], '[adobe]'),
            ]

            def get_category(proc_name: str) -> str:
                """Match keywords at word boundaries only — not embedded mid-word."""
                base = proc_name.lower()
                for suffix in ('.exe', '.x64', '.x86', '.x32'):
                    if base.endswith(suffix):
                        base = base[:-len(suffix)]
                        break
                for keywords, label in category_map:
                    for kw in keywords:
                        if kw not in base:
                            continue
                        idx = base.index(kw)
                        prefix_ok = (idx == 0 or not base[idx - 1].isalpha())
                        suffix_ok = (idx + len(kw) >= len(base) or not base[idx + len(kw)].isalpha())
                        if prefix_ok or suffix_ok:
                            return label
                return ''

            def path_suggests_game_install(exe: str) -> bool:
                """True when exe lives under a typical PC game install folder (name-based tag missed many titles)."""
                el = (exe or "").lower().replace("/", "\\")
                if not el:
                    return False
                markers = (
                    "steamapps\\common",
                    "\\epic games\\",
                    "\\riot games\\",
                    "\\ubisoft\\",
                    "\\ubisoft game launcher\\",
                    "ea games\\",
                    "electronic arts\\",
                    "battle.net\\",
                    "blizzard\\",
                    "gog galaxy\\",
                    "\\xboxgames\\",
                    "rockstar games\\",
                    "bethesda.net\\",
                )
                return any(m in el for m in markers)

            def short_exe_hint(exe: Optional[str]) -> str:
                """Last path segments so the model can map game/app titles to install folders."""
                if not exe or not isinstance(exe, str):
                    return ""
                try:
                    p = exe.replace("/", "\\").strip()
                    parts = [x for x in p.split("\\") if x]
                    if len(parts) >= 3:
                        return "\\".join(parts[-3:])
                    if parts:
                        return "\\".join(parts)
                except Exception:
                    pass
                return ""

            # Sort: categorized apps first, then by memory (games/media tend to be heavy)
            rows: List[Tuple[Dict[str, Any], str, float]] = []
            for proc in processes:
                proc_name = proc.get("name") or "Unknown"
                cat = get_category(proc_name.lower())
                if not cat and path_suggests_game_install(proc.get("exe") or ""):
                    cat = "[game]"
                mem = float(proc.get("memory_percent") or 0)
                rows.append((proc, cat, mem))

            rows.sort(key=lambda r: (not bool(r[1]), -r[2], (r[0].get("name") or "").lower()))

            max_lines = 150
            process_list: List[str] = []
            for proc, category, _mem in rows[:max_lines]:
                proc_name = proc.get("name", "Unknown")
                pid = proc.get("pid")
                cat_suffix = f" {category}" if category else ""
                hint = short_exe_hint(proc.get("exe"))
                path_part = f" | {hint}" if hint else ""
                process_list.append(f"{proc_name} (PID: {pid}){cat_suffix}{path_part}")

            return {
                "installed_apps": app_list[:80],
                "running_processes": process_list,
                "total_apps": len(apps),
                "total_processes": len(processes)
            }
        
        except Exception as e:
            logger.error(f"Error building AI context: {e}")
            return {
                "installed_apps": [],
                "running_processes": [],
                "total_apps": 0,
                "total_processes": 0
            }
    
    async def find_app(self, app_name: str) -> Optional[Dict[str, Any]]:
        """
        Find application by name
        
        Args:
            app_name: Application name to search for
            
        Returns:
            App info dict or None if not found
        """
        apps = await self.get_installed_apps()
        app_name_lower = app_name.lower().strip()
        
        # Try exact match first
        if app_name_lower in apps:
            return apps[app_name_lower]
        
        # Try fuzzy match
        from difflib import get_close_matches
        matches = get_close_matches(app_name_lower, apps.keys(), n=1, cutoff=0.6)
        
        if matches:
            return apps[matches[0]]
        
        return None
    
    async def find_process(self, process_name: str) -> List[Dict[str, Any]]:
        """
        Find running process(es) by name, path substring, or fuzzy name match.
        """
        processes = await self.get_running_processes(simplified=False)
        process_name_lower = process_name.lower().strip()
        
        if process_name_lower.endswith('.exe'):
            process_name_lower = process_name_lower[:-4]
        
        matches: List[Dict[str, Any]] = []
        seen_pids = set()
        
        def add(proc: Dict[str, Any]):
            pid = proc.get("pid")
            if pid is not None and pid in seen_pids:
                return
            if pid is not None:
                seen_pids.add(pid)
            matches.append(proc)
        
        stop_tokens = {
            "that", "this", "with", "from", "your", "game", "games", "running", "close", "kill",
            "open", "the", "are", "what", "which", "where", "when", "here", "there", "please",
            "fucking", "damn", "hell",
        }
        path_tokens = [
            t for t in re.findall(r"[a-z]{4,}", process_name_lower)
            if t not in stop_tokens
        ]

        for proc in processes:
            proc_name = proc['name'].lower()
            name_core = proc_name[:-4] if proc_name.endswith('.exe') else proc_name
            path = (proc.get('path') or '').lower()
            path_norm = path.replace("/", "\\")
            if process_name_lower in proc_name or process_name_lower in name_core:
                add(proc)
            elif path_norm and process_name_lower in path_norm:
                add(proc)
            elif path_norm and path_tokens:
                compact = path_norm.replace(" ", "")
                if any(len(t) >= 4 and t in compact for t in path_tokens):
                    add(proc)
        
        if not matches and process_name_lower:
            name_cores = []
            for proc in processes:
                pn = proc['name'].lower()
                name_cores.append(pn[:-4] if pn.endswith('.exe') else pn)
            fuzzy = get_close_matches(process_name_lower, name_cores, n=8, cutoff=0.5)
            for proc in processes:
                pn = proc['name'].lower()
                core = pn[:-4] if pn.endswith('.exe') else pn
                if core in fuzzy:
                    add(proc)
        
        return matches


# Global instance
_system_context: Optional[SystemContextProvider] = None


def get_system_context() -> SystemContextProvider:
    """Get or create global system context provider"""
    global _system_context
    if _system_context is None:
        _system_context = SystemContextProvider()
    return _system_context
