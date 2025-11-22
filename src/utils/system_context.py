"""
System Context Provider
Provides AI with information about installed apps and running processes
"""
import os
import winreg
import glob
import psutil
import json
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path

from src.database.redis_client import get_redis_client
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SystemContextProvider:
    """Provides system context (apps, processes) to AI for better decision making"""
    
    CACHE_FILE = "system_context_cache.json"
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
                        except:
                            pass
                        return cached_data
            except Exception as e:
                logger.debug(f"File cache read failed: {e}")
        
        # Perform scan
        logger.info("Scanning installed applications...")
        apps = {}
        
        # 1. Built-in Windows apps
        apps.update(self._get_builtin_apps())
        
        # 2. Registry-based apps
        apps.update(self._get_registry_apps())
        
        # 3. Start menu shortcuts
        apps.update(self._get_startmenu_apps())
        
        logger.info(f"Found {len(apps)} installed applications")
        
        # Cache results
        try:
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
                            "status": info.get('status', 'unknown')
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
            for key, app in sorted(apps.items(), key=lambda x: x[1]['display_name'].lower()):
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
            
            # Prioritize common user apps that might be killed
            priority_processes = []
            other_processes = []
            
            priority_keywords = [
                'chrome', 'firefox', 'edge', 'brave', 'opera',  # Browsers
                'spotify', 'discord', 'teams', 'slack', 'zoom',  # Communication/Media
                'vscode', 'code', 'pycharm', 'studio', 'notepad',  # Editors
                'python', 'node', 'java', 'dotnet', 'powershell', 'cmd',  # Development
                'obs', 'streamlabs', 'nvidia', 'radeon',  # Gaming/Recording
                'steam', 'epic', 'origin', 'uplay', 'battle',  # Gaming platforms
                'cursor', 'sublime', 'atom', 'brackets',  # More editors
                'postman', 'docker', 'git',  # Dev tools
                'excel', 'word', 'outlook', 'powerpoint',  # Office
                'premiere', 'photoshop', 'illustrator', 'after effects',  # Adobe
            ]
            
            for proc in processes:
                proc_name = proc["name"]
                proc_lower = proc_name.lower()
                proc_info = f"{proc_name} (PID: {proc['pid']})"
                
                if any(keyword in proc_lower for keyword in priority_keywords):
                    priority_processes.append(proc_info)
                else:
                    other_processes.append(proc_info)
            
            # Combine: priority first, then others (up to 60 total)
            process_list = sorted(priority_processes) + sorted(other_processes)
            
            return {
                "installed_apps": app_list[:80],  # Limit to 80 with paths
                "running_processes": process_list[:60],  # Increased to 60 with smart prioritization
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
        Find running process(es) by name
        
        Args:
            process_name: Process name to search for
            
        Returns:
            List of matching processes
        """
        processes = await self.get_running_processes(simplified=False)
        process_name_lower = process_name.lower().strip()
        
        # Remove .exe if present for matching
        if process_name_lower.endswith('.exe'):
            process_name_lower = process_name_lower[:-4]
        
        matches = []
        for proc in processes:
            proc_name = proc['name'].lower()
            if process_name_lower in proc_name or process_name_lower in proc_name.replace('.exe', ''):
                matches.append(proc)
        
        return matches


# Global instance
_system_context: Optional[SystemContextProvider] = None


def get_system_context() -> SystemContextProvider:
    """Get or create global system context provider"""
    global _system_context
    if _system_context is None:
        _system_context = SystemContextProvider()
    return _system_context
