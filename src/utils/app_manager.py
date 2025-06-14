"""
App Manager for Aiden
Provides intelligent app discovery, searching, and launching using get-installed-apps
"""
import os
import sys
import logging
import subprocess
import json
from typing import List, Dict, Any, Optional
import difflib

class AppManager:
    """Manages application discovery, searching, and launching"""
    
    def __init__(self, config_manager=None):
        """Initialize the app manager
        
        Args:
            config_manager: Configuration manager instance
        """
        self.config_manager = config_manager
        self._installed_apps = []
        self._apps_cache_valid = False
        self._common_app_mappings = {
            # Browser mappings
            "chrome": ["Google Chrome", "Chrome", "chrome"],
            "firefox": ["Firefox", "Mozilla Firefox", "firefox"],
            "edge": ["Microsoft Edge", "Edge", "msedge"],
            "safari": ["Safari", "safari"],
            "opera": ["Opera", "opera"],
            
            # Development tools
            "vscode": ["Visual Studio Code", "Code", "VS Code", "Microsoft Visual Studio Code"],
            "code": ["Visual Studio Code", "Code", "VS Code", "Microsoft Visual Studio Code"],
            "visual studio": ["Microsoft Visual Studio", "Visual Studio"],
            "atom": ["Atom", "atom"],
            "sublime": ["Sublime Text", "sublime"],
            "notepad++": ["Notepad++", "notepad++"],
            "pycharm": ["PyCharm", "pycharm"],
            "intellij": ["IntelliJ IDEA", "intellij"],
            
            # Office applications
            "word": ["Microsoft Word", "Word", "winword"],
            "excel": ["Microsoft Excel", "Excel", "excel"],
            "powerpoint": ["Microsoft PowerPoint", "PowerPoint", "powerpnt"],
            "outlook": ["Microsoft Outlook", "Outlook", "outlook"],
            "teams": ["Microsoft Teams", "Teams", "ms-teams"],
            
            # Media and communication
            "discord": ["Discord", "discord"],
            "slack": ["Slack", "slack"],
            "spotify": ["Spotify", "spotify"],
            "vlc": ["VLC Media Player", "VLC", "vlc"],
            "zoom": ["Zoom", "zoom"],
            "skype": ["Skype", "skype"],
            
            # System tools
            "notepad": ["Notepad", "notepad"],
            "calculator": ["Calculator", "calc"],
            "explorer": ["File Explorer", "Windows Explorer", "explorer"],
            "terminal": ["Command Prompt", "Terminal", "cmd"],
            "powershell": ["PowerShell", "Windows PowerShell", "powershell"],
            "paint": ["Paint", "Microsoft Paint", "mspaint"],
            
            # Gaming and entertainment
            "steam": ["Steam", "steam"],
            "epic": ["Epic Games Launcher", "Epic Games", "epic"],
            "origin": ["Origin", "EA Origin", "origin"],
            "obs": ["OBS Studio", "OBS", "obs64"],
            
            # Productivity
            "notion": ["Notion", "notion"],
            "obsidian": ["Obsidian", "obsidian"],
            "evernote": ["Evernote", "evernote"],
            "onenote": ["OneNote", "Microsoft OneNote", "onenote"],
        }
        
        logging.info("App manager initialized")
    
    def get_installed_apps(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Get list of installed applications
        
        Args:
            force_refresh: Force refresh of the apps cache
            
        Returns:
            List of installed applications with metadata
        """
        if not self._apps_cache_valid or force_refresh:
            self._refresh_apps_cache()
        
        return self._installed_apps
    
    def _refresh_apps_cache(self):
        """Refresh the installed apps cache using get-installed-apps"""
        try:
            # Import the Node.js package functionality
            import subprocess
            import json
            
            # Create a temporary Node.js script to get installed apps
            script_content = '''
const { getInstalledApps } = require('get-installed-apps');

getInstalledApps().then(apps => {
    console.log(JSON.stringify(apps, null, 0));
}).catch(error => {
    console.error('Error:', error.message);
    process.exit(1);
});
'''
            
            # Write temporary script
            script_path = os.path.join(os.getcwd(), 'temp_get_apps.js')
            with open(script_path, 'w') as f:
                f.write(script_content)
            
            try:
                # Run the Node.js script
                result = subprocess.run(
                    ['node', script_path],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=os.getcwd()
                )
                
                if result.returncode == 0:
                    # Parse the JSON output
                    apps_data = json.loads(result.stdout.strip())
                    
                    # Process and normalize the app data
                    processed_apps = self._process_apps_data(apps_data)
                    
                    # Add common system apps that might not be detected
                    self._add_common_system_apps(processed_apps)
                    
                    self._installed_apps = processed_apps
                    self._apps_cache_valid = True
                    
                    logging.info(f"Successfully loaded {len(self._installed_apps)} installed applications")
                else:
                    logging.error(f"Error running get-installed-apps: {result.stderr}")
                    self._fallback_to_common_apps()
                    
            finally:
                # Clean up temporary script
                if os.path.exists(script_path):
                    os.remove(script_path)
                    
        except Exception as e:
            logging.error(f"Error refreshing apps cache: {e}")
            self._fallback_to_common_apps()
    
    def _process_apps_data(self, apps_data: List[Dict]) -> List[Dict[str, Any]]:
        """Process and normalize app data from get-installed-apps
        
        Args:
            apps_data: Raw app data from get-installed-apps
            
        Returns:
            Processed and normalized app data
        """
        processed_apps = []
        
        for app in apps_data:
            try:
                # Extract key information
                app_name = app.get('appName') or app.get('DisplayName', 'Unknown')
                app_version = app.get('appVersion') or app.get('DisplayVersion', 'Unknown')
                app_publisher = app.get('appPublisher') or app.get('Publisher', 'Unknown')
                install_location = app.get('InstallLocation', '')
                display_icon = app.get('DisplayIcon', '')
                
                # Skip system components and updates
                if self._should_skip_app(app_name, app_publisher):
                    continue
                
                # Skip if this looks like an installer/uninstaller based on name
                if self._is_unwanted_app_type(app_name):
                    continue
                
                # Create normalized app entry
                processed_app = {
                    'name': app_name,
                    'version': app_version,
                    'publisher': app_publisher,
                    'install_location': install_location,
                    'icon': display_icon,
                    'executable': self._extract_executable(app, install_location),
                    'keywords': self._generate_keywords(app_name),
                    'raw_data': app  # Keep original data for reference
                }
                
                processed_apps.append(processed_app)
                
            except Exception as e:
                logging.warning(f"Error processing app data: {e}")
                continue
        
        # Sort by name for better organization
        processed_apps.sort(key=lambda x: x['name'].lower())
        
        return processed_apps
    
    def _should_skip_app(self, app_name: str, publisher: str) -> bool:
        """Determine if an app should be skipped from the list
        
        Args:
            app_name: Application name
            publisher: Application publisher
            
        Returns:
            True if app should be skipped
        """
        skip_patterns = [
            # System components
            'microsoft visual c++',
            'microsoft .net',
            'windows sdk',
            'redistributable',
            'runtime',
            'update for',
            'security update',
            'hotfix',
            'kb[0-9]',
            'microsoft system clr types',
            'microsoft sql server',
            'microsoft office shared',
            'microsoft visual studio installer',
            'windows driver package',
            
            # Installers and uninstallers
            'uninstall',
            'unins',
            'installer',
            'setup',
            'updater',
            'launcher prerequisites',
            'installation',
            
            # System utilities that shouldn't be launched
            'driver',
            'service',
            'framework',
            'library',
            'component',
            'package',
            'tools for',
            'add-in',
            'extension',
            'plugin',
            
            # Version-specific patterns
            'x64',
            'x86',
            '(64-bit)',
            '(32-bit)',
            'prerequisites',
            'redist'
        ]
        
        app_lower = app_name.lower()
        
        # Check skip patterns
        for pattern in skip_patterns:
            if pattern in app_lower:
                return True
        
        # Skip very short names that are likely system components
        if len(app_name.strip()) < 3:
            return True
        
        # Skip apps that are clearly uninstallers (common patterns)
        uninstaller_indicators = [
            'uninstall',
            'remove',
            'cleanup',
            'unins'
        ]
        
        for indicator in uninstaller_indicators:
            if app_lower.startswith(indicator) or app_lower.endswith(indicator):
                return True
        
        # Skip if it's clearly an installer
        installer_indicators = [
            'installer',
            'setup',
            'install'
        ]
        
        for indicator in installer_indicators:
            if app_lower.endswith(indicator) or f' {indicator}' in app_lower:
                return True
            
        return False
    
    def _extract_executable(self, app_data: Dict, install_location: str) -> str:
        """Extract executable name/path from app data
        
        Args:
            app_data: Raw app data
            install_location: Installation location
            
        Returns:
            Executable name or path
        """
        app_name = app_data.get('appName') or app_data.get('DisplayName', '')
        
        # Try to get from display icon first (usually points to main executable)
        display_icon = app_data.get('DisplayIcon', '')
        if display_icon and display_icon.endswith('.exe'):
            exe_name = os.path.basename(display_icon).replace('.exe', '')
            # Skip if it looks like an installer/uninstaller
            if not self._is_installer_executable(display_icon):
                return exe_name
        
        # Try to find main executable in install location
        if install_location and os.path.exists(install_location):
            try:
                for file in os.listdir(install_location):
                    if file.endswith('.exe'):
                        exe_path = os.path.join(install_location, file)
                        # Skip installers/uninstallers
                        if not self._is_installer_executable(exe_path):
                            return file.replace('.exe', '')
            except (OSError, PermissionError):
                pass
        
        # Try to extract from uninstall string (but avoid uninstaller executables)
        uninstall_string = app_data.get('UninstallString', '')
        if uninstall_string:
            import re
            # Look for quoted executable paths
            matches = re.findall(r'"([^"]+\.exe)"', uninstall_string)
            for match in matches:
                if not self._is_installer_executable(match):
                    return os.path.basename(match).replace('.exe', '')
        
        # Generate executable name from app name
        app_name_clean = app_name.lower().replace(' ', '').replace('-', '').replace('_', '')
        
        # Handle common app name patterns
        if 'steam' in app_name_clean:
            return 'steam'
        elif 'calculator' in app_name_clean or app_name_clean == 'calc':
            return 'calc'
        elif 'postman' in app_name_clean:
            return 'postman'
        elif 'chrome' in app_name_clean:
            return 'chrome'
        elif 'firefox' in app_name_clean:
            return 'firefox'
        elif 'edge' in app_name_clean:
            return 'msedge'
        elif 'code' in app_name_clean or 'vscode' in app_name_clean:
            return 'code'
        elif 'notepad' in app_name_clean:
            return 'notepad'
        elif 'explorer' in app_name_clean:
            return 'explorer'
        elif 'powershell' in app_name_clean:
            return 'powershell'
        elif 'paint' in app_name_clean:
            return 'mspaint'
        
        # Fallback to cleaned app name
        return app_name_clean
    
    def _generate_keywords(self, app_name: str) -> List[str]:
        """Generate search keywords for an app
        
        Args:
            app_name: Application name
            
        Returns:
            List of search keywords
        """
        keywords = []
        
        # Add the full name
        keywords.append(app_name.lower())
        
        # Add individual words
        words = app_name.lower().split()
        keywords.extend(words)
        
        # Add without common prefixes/suffixes
        clean_name = app_name.lower()
        for prefix in ['microsoft ', 'adobe ', 'google ', 'mozilla ']:
            if clean_name.startswith(prefix):
                clean_name = clean_name[len(prefix):]
                keywords.append(clean_name)
                break
        
        # Add acronyms
        if len(words) > 1:
            acronym = ''.join(word[0] for word in words if word)
            if len(acronym) > 1:
                keywords.append(acronym)
        
        return list(set(keywords))  # Remove duplicates
    
    def _add_common_system_apps(self, processed_apps: List[Dict[str, Any]]):
        """Add common system apps that might not be detected by get-installed-apps
        
        Args:
            processed_apps: List of processed apps to add to
        """
        # Get list of existing app names to avoid duplicates
        existing_names = {app['name'].lower() for app in processed_apps}
        
        # Common system apps that should always be available
        system_apps = [
            {"name": "Calculator", "executable": "calc", "keywords": ["calculator", "calc", "math"]},
            {"name": "Notepad", "executable": "notepad", "keywords": ["notepad", "text", "editor"]},
            {"name": "File Explorer", "executable": "explorer", "keywords": ["explorer", "files", "folder"]},
            {"name": "Command Prompt", "executable": "cmd", "keywords": ["cmd", "terminal", "command"]},
            {"name": "PowerShell", "executable": "powershell", "keywords": ["powershell", "terminal", "shell"]},
            {"name": "Paint", "executable": "mspaint", "keywords": ["paint", "drawing", "image"]},
        ]
        
        for app in system_apps:
            if app['name'].lower() not in existing_names:
                processed_app = {
                    'name': app['name'],
                    'version': 'System',
                    'publisher': 'Microsoft',
                    'install_location': '',
                    'icon': '',
                    'executable': app['executable'],
                    'keywords': app['keywords'],
                    'raw_data': {}
                }
                processed_apps.append(processed_app)
                logging.debug(f"Added system app: {app['name']}")
    
    def _is_unwanted_app_type(self, app_name: str) -> bool:
        """Check if app is an unwanted type (installer, uninstaller, etc.)
        
        Args:
            app_name: Application name
            
        Returns:
            True if app should be deprioritized
        """
        unwanted_indicators = [
            'uninstall', 'unins', 'installer', 'setup', 'updater',
            'prerequisites', 'redist', 'runtime', 'framework',
            'driver', 'service', 'component', 'package'
        ]
        
        app_lower = app_name.lower()
        return any(indicator in app_lower for indicator in unwanted_indicators)
    
    def _normalize_app_query(self, query: str) -> str:
        """Normalize user query for better matching
        
        Args:
            query: User search query
            
        Returns:
            Normalized query
        """
        # Common query mappings
        query_mappings = {
            'calc': 'calculator',
            'calculator': 'calculator',
            'steam': 'steam',
            'postman': 'postman',
            'chrome': 'chrome',
            'firefox': 'firefox',
            'edge': 'edge',
            'vscode': 'visual studio code',
            'code': 'visual studio code',
            'vs code': 'visual studio code',
            'notepad': 'notepad',
            'explorer': 'file explorer',
            'cmd': 'command prompt',
            'terminal': 'command prompt',
            'powershell': 'powershell',
            'paint': 'paint',
            'word': 'microsoft word',
            'excel': 'microsoft excel',
            'powerpoint': 'microsoft powerpoint',
            'outlook': 'microsoft outlook',
            'teams': 'microsoft teams',
            'discord': 'discord',
            'spotify': 'spotify',
            'vlc': 'vlc media player',
            'obs': 'obs studio'
        }
        
        normalized = query.lower().strip()
        return query_mappings.get(normalized, normalized)
    
    def _normalize_app_name(self, app_name: str) -> str:
        """Normalize app name for better matching
        
        Args:
            app_name: Application name
            
        Returns:
            Normalized app name
        """
        normalized = app_name.lower().strip()
        
        # Remove common prefixes
        prefixes_to_remove = [
            'microsoft ', 'adobe ', 'google ', 'mozilla ',
            'jetbrains ', 'oracle ', 'apple '
        ]
        
        for prefix in prefixes_to_remove:
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):]
                break
        
        # Remove version numbers and extra info
        import re
        normalized = re.sub(r'\s+\d+[\d.]*', '', normalized)  # Remove version numbers
        normalized = re.sub(r'\s*\([^)]*\)', '', normalized)  # Remove parenthetical info
        normalized = re.sub(r'\s*-\s*.*$', '', normalized)    # Remove dash and everything after
        
        return normalized.strip()
    
    def _is_common_app_alias(self, query: str, app_name: str) -> bool:
        """Check if query is a common alias for the app
        
        Args:
            query: User search query
            app_name: Application name
            
        Returns:
            True if query is a known alias for the app
        """
        app_aliases = {
            'calculator': ['calc', 'calculator'],
            'steam': ['steam'],
            'postman': ['postman'],
            'chrome': ['chrome', 'google chrome'],
            'firefox': ['firefox', 'mozilla firefox'],
            'edge': ['edge', 'microsoft edge'],
            'visual studio code': ['vscode', 'vs code', 'code'],
            'notepad': ['notepad'],
            'file explorer': ['explorer', 'files'],
            'command prompt': ['cmd', 'terminal'],
            'powershell': ['powershell', 'pwsh'],
            'paint': ['paint', 'mspaint'],
            'discord': ['discord'],
            'spotify': ['spotify'],
            'vlc media player': ['vlc'],
            'obs studio': ['obs']
        }
        
        query_lower = query.lower()
        app_lower = app_name.lower()
        
        for canonical_name, aliases in app_aliases.items():
            if query_lower in aliases and canonical_name in app_lower:
                return True
        
        return False
    
    def _fallback_to_common_apps(self):
        """Fallback to common apps list if get-installed-apps fails"""
        logging.warning("Falling back to common apps list")
        
        common_apps = [
            {"name": "Google Chrome", "executable": "chrome", "keywords": ["chrome", "google", "browser"]},
            {"name": "Microsoft Edge", "executable": "msedge", "keywords": ["edge", "microsoft", "browser"]},
            {"name": "Firefox", "executable": "firefox", "keywords": ["firefox", "mozilla", "browser"]},
            {"name": "Visual Studio Code", "executable": "code", "keywords": ["vscode", "code", "vs", "editor"]},
            {"name": "Notepad", "executable": "notepad", "keywords": ["notepad", "text", "editor"]},
            {"name": "Calculator", "executable": "calc", "keywords": ["calculator", "calc", "math"]},
            {"name": "File Explorer", "executable": "explorer", "keywords": ["explorer", "files", "folder"]},
            {"name": "Command Prompt", "executable": "cmd", "keywords": ["cmd", "terminal", "command"]},
            {"name": "PowerShell", "executable": "powershell", "keywords": ["powershell", "terminal", "shell"]},
            {"name": "Windows PowerShell", "executable": "powershell", "keywords": ["powershell", "terminal", "shell"]},
            {"name": "Paint", "executable": "mspaint", "keywords": ["paint", "drawing", "image"]},
            {"name": "Steam", "executable": "steam", "keywords": ["steam", "games", "gaming"]},
            {"name": "Postman", "executable": "postman", "keywords": ["postman", "api", "development"]},
        ]
        
        self._installed_apps = [
            {
                'name': app['name'],
                'version': 'Unknown',
                'publisher': 'Unknown',
                'install_location': '',
                'icon': '',
                'executable': app['executable'],
                'keywords': app['keywords'],
                'raw_data': {}
            }
            for app in common_apps
        ]
        
        self._apps_cache_valid = True
    
    def search_apps(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search for applications by name or keywords
        
        Args:
            query: Search query
            limit: Maximum number of results to return
            
        Returns:
            List of matching applications sorted by relevance
        """
        if not self._apps_cache_valid:
            self.get_installed_apps()
        
        query_lower = query.lower().strip()
        matches = []
        
        for app in self._installed_apps:
            score = self._calculate_match_score(app, query_lower)
            if score > 0:
                matches.append((app, score))
        
        # Sort by score (descending) and return top results
        matches.sort(key=lambda x: x[1], reverse=True)
        return [match[0] for match in matches[:limit]]
    
    def _calculate_match_score(self, app: Dict[str, Any], query: str) -> float:
        """Calculate match score for an app against a query
        
        Args:
            app: Application data
            query: Search query
            
        Returns:
            Match score (higher is better, 0 means no match)
        """
        score = 0.0
        app_name = app['name'].lower()
        keywords = app.get('keywords', [])
        
        # Skip apps that are clearly not what the user wants
        if self._is_unwanted_app_type(app_name):
            return 0.0
        
        # Handle common app name mappings
        normalized_query = self._normalize_app_query(query)
        normalized_name = self._normalize_app_name(app_name)
        
        # Exact normalized match (highest score)
        if normalized_query == normalized_name:
            return 100.0
        
        # Exact name match
        if query == app_name:
            return 95.0
        
        # Check for common app aliases
        if self._is_common_app_alias(query, app_name):
            return 90.0
        
        # Name starts with query
        if app_name.startswith(query):
            score += 80.0
        
        # Normalized name starts with normalized query
        if normalized_name.startswith(normalized_query):
            score += 75.0
        
        # Query is in name
        if query in app_name:
            score += 60.0
        
        # Normalized query in normalized name
        if normalized_query in normalized_name:
            score += 55.0
        
        # Check keywords
        for keyword in keywords:
            if query == keyword:
                score += 70.0
            elif keyword.startswith(query):
                score += 50.0
            elif query in keyword:
                score += 30.0
        
        # Check common mappings (using the alias system)
        if self._is_common_app_alias(query, app_name):
            score += 85.0
        
        # Fuzzy matching for typos
        if score == 0:
            similarity = difflib.SequenceMatcher(None, query, app_name).ratio()
            if similarity > 0.6:
                score += similarity * 40.0
        
        return score
    
    def find_app_by_name(self, app_name: str) -> Optional[Dict[str, Any]]:
        """Find a specific app by name
        
        Args:
            app_name: Application name to search for
            
        Returns:
            App data if found, None otherwise
        """
        results = self.search_apps(app_name, limit=1)
        return results[0] if results else None
    
    def launch_app(self, app_data: Dict[str, Any]) -> bool:
        """Launch an application
        
        Args:
            app_data: Application data from search results
            
        Returns:
            True if launched successfully, False otherwise
        """
        try:
            executable = app_data.get('executable', '')
            install_location = app_data.get('install_location', '')
            app_name = app_data.get('name', '')
            raw_data = app_data.get('raw_data', {})
            
            # Double-check that this isn't an installer/uninstaller
            if self._is_unwanted_app_type(app_name):
                logging.warning(f"Refusing to launch unwanted app type: {app_name}")
                return False
            
            # Try different launch methods in order of preference
            success = False
            
            # Method 1: Try to find the main executable in install location
            if install_location and os.path.exists(install_location):
                # Look for common executable patterns
                potential_exes = []
                
                # Add the extracted executable name
                if executable:
                    potential_exes.extend([
                        f"{executable}.exe",
                        f"{executable}",
                        f"{app_name.replace(' ', '')}.exe",
                        f"{app_name.replace(' ', '').lower()}.exe"
                    ])
                
                # Add common patterns based on app name
                app_name_clean = app_name.lower().replace(' ', '').replace('-', '')
                potential_exes.extend([
                    f"{app_name_clean}.exe",
                    f"{app_name.split()[0].lower()}.exe"  # First word of app name
                ])
                
                # Try each potential executable
                for exe_name in potential_exes:
                    exe_path = os.path.join(install_location, exe_name)
                    if os.path.exists(exe_path) and not self._is_installer_executable(exe_path):
                        try:
                            subprocess.Popen([exe_path], cwd=install_location)
                            success = True
                            logging.info(f"Launched {app_name} from: {exe_path}")
                            break
                        except Exception as e:
                            logging.debug(f"Failed to launch {exe_path}: {e}")
                            continue
            
            # Method 2: Try with Windows start command (most reliable for installed apps)
            if not success and os.name == 'nt' and executable:
                try:
                    # Use start command which handles PATH and registry entries
                    subprocess.Popen(f'start "" "{executable}"', shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
                    success = True
                    logging.info(f"Launched {app_name} with start command: {executable}")
                except Exception as e:
                    logging.debug(f"Start command failed for {executable}: {e}")
            
            # Method 3: Try common app mappings for system apps
            if not success:
                app_lower = app_name.lower()
                system_commands = {
                    'calculator': 'calc',
                    'notepad': 'notepad',
                    'paint': 'mspaint',
                    'file explorer': 'explorer',
                    'command prompt': 'cmd',
                    'powershell': 'powershell'
                }
                
                for app_key, cmd in system_commands.items():
                    if app_key in app_lower:
                        try:
                            subprocess.Popen(cmd, shell=True)
                            success = True
                            logging.info(f"Launched {app_name} with system command: {cmd}")
                            break
                        except Exception as e:
                            logging.debug(f"System command failed for {cmd}: {e}")
            
            # Method 4: Try direct executable name
            if not success and executable:
                try:
                    subprocess.Popen(executable, shell=True)
                    success = True
                    logging.info(f"Launched {app_name} with direct executable: {executable}")
                except Exception as e:
                    logging.debug(f"Direct executable failed for {executable}: {e}")
            
            # Method 5: Try with .exe extension
            if not success and executable and os.name == 'nt':
                try:
                    exe_name = f"{executable}.exe" if not executable.endswith('.exe') else executable
                    subprocess.Popen(exe_name, shell=True)
                    success = True
                    logging.info(f"Launched {app_name} with .exe extension: {exe_name}")
                except Exception as e:
                    logging.debug(f"Exe extension failed for {exe_name}: {e}")
            
            if not success:
                logging.error(f"Failed to launch {app_name} - all methods exhausted")
                logging.debug(f"App data: executable='{executable}', install_location='{install_location}'")
            
            return success
            
        except Exception as e:
            logging.error(f"Error launching app {app_data.get('name', 'Unknown')}: {e}")
            return False
    
    def _is_installer_executable(self, exe_path: str) -> bool:
        """Check if an executable is likely an installer/uninstaller
        
        Args:
            exe_path: Path to executable
            
        Returns:
            True if it's likely an installer/uninstaller
        """
        exe_name = os.path.basename(exe_path).lower()
        installer_patterns = [
            'setup', 'install', 'uninstall', 'unins', 'updater',
            'installer', 'uninst', 'remove', 'cleanup'
        ]
        
        return any(pattern in exe_name for pattern in installer_patterns)
    
    def get_app_categories(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get apps organized by categories
        
        Returns:
            Dictionary of categories with their apps
        """
        if not self._apps_cache_valid:
            self.get_installed_apps()
        
        categories = {
            "Browsers": [],
            "Development": [],
            "Office": [],
            "Media": [],
            "Communication": [],
            "Games": [],
            "System": [],
            "Other": []
        }
        
        for app in self._installed_apps:
            app_name = app['name'].lower()
            category = "Other"  # Default category
            
            # Categorize based on name and keywords
            if any(browser in app_name for browser in ['chrome', 'firefox', 'edge', 'safari', 'opera', 'browser']):
                category = "Browsers"
            elif any(dev in app_name for dev in ['visual studio', 'code', 'pycharm', 'intellij', 'atom', 'sublime', 'git', 'node']):
                category = "Development"
            elif any(office in app_name for office in ['word', 'excel', 'powerpoint', 'outlook', 'office', 'teams']):
                category = "Office"
            elif any(media in app_name for media in ['vlc', 'spotify', 'media', 'player', 'music', 'video']):
                category = "Media"
            elif any(comm in app_name for comm in ['discord', 'slack', 'zoom', 'skype', 'telegram', 'whatsapp']):
                category = "Communication"
            elif any(game in app_name for game in ['steam', 'epic', 'origin', 'game', 'gaming']):
                category = "Games"
            elif any(system in app_name for system in ['explorer', 'notepad', 'calculator', 'cmd', 'powershell', 'paint']):
                category = "System"
            
            categories[category].append(app)
        
        # Sort each category by name
        for category in categories:
            categories[category].sort(key=lambda x: x['name'])
        
        return categories
    
    def get_recently_used_apps(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get recently used applications (placeholder for future implementation)
        
        Args:
            limit: Maximum number of apps to return
            
        Returns:
            List of recently used apps
        """
        # This is a placeholder - in a full implementation, this would track
        # app usage and return the most recently used applications
        popular_apps = ['chrome', 'vscode', 'discord', 'spotify', 'explorer']
        
        recent_apps = []
        for app_name in popular_apps:
            app = self.find_app_by_name(app_name)
            if app:
                recent_apps.append(app)
            if len(recent_apps) >= limit:
                break
        
        return recent_apps 