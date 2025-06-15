"""
Configuration Manager for Aiden
Handles loading and saving of configuration settings and user profiles
"""
import json
import os
import logging
from datetime import datetime
from typing import Dict, Any, Optional

class ConfigManager:
    """Manages application configuration and user profiles"""
    
    def __init__(self, config_path: str = "config/config.json"):
        """Initialize the configuration manager
        
        Args:
            config_path: Path to the main configuration file
        """
        # Get the project root directory
        self.project_root = self._get_project_root()
        
        # Use absolute paths for configuration files
        self.config_path = os.path.join(self.project_root, config_path)
        self.config = self._load_json(self.config_path)
          # Load user profile
        user_profile_rel_path = self.config["memory"]["user_profile"]
        self.user_profile_path = os.path.join(self.project_root, user_profile_rel_path)
        self.user_profile = self._load_json(self.user_profile_path)
          # Set up logging
        self._setup_logging()
        
        logging.info(f"Configuration loaded from {config_path}")
        logging.info(f"User profile loaded for {self.user_profile['personal']['name']}")
        
    def _get_project_root(self) -> str:
        """Get the absolute path to the project root directory
        
        Returns:
            Absolute path to the project root directory
        """
        # Navigate up from current file location to find project root
        # src/utils/config_manager.py -> src/utils -> src -> project_root
        current_dir = os.path.dirname(os.path.abspath(__file__))  # src/utils
        src_dir = os.path.dirname(current_dir)  # src
        project_root = os.path.dirname(src_dir)  # project_root
        return project_root
            
    def _load_json(self, file_path: str) -> Dict[str, Any]:
        """Load a JSON file
        
        Args:
            file_path: Path to the JSON file
            
        Returns:
            Dictionary containing the JSON data
        """
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logging.error(f"File not found: {file_path}")
            raise
        except json.JSONDecodeError:
            logging.error(f"Invalid JSON in file: {file_path}")
            raise
    
    def _save_json(self, data: Dict[str, Any], file_path: str) -> None:
        """Save data to a JSON file
        
        Args:
            data: Dictionary to save
            file_path: Path to save the JSON file
        """
        try:
            # Ensure the directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logging.error(f"Error saving to {file_path}: {e}")
            raise
    
    def _setup_logging(self) -> None:
        """Configure logging based on settings"""
        log_file = self.config["general"]["log_file"]
        log_level = getattr(logging, self.config["general"]["log_level"])
        
        # Ensure log directory exists
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
    
    def get_config(self, section: Optional[str] = None) -> Dict[str, Any]:
        """Get configuration settings
        
        Args:
            section: Optional section name, if None returns entire config
            
        Returns:
            Dictionary of configuration settings
        """
        if section:
            return self.config.get(section, {})
        return self.config
    
    def get_user_profile(self, section: Optional[str] = None) -> Dict[str, Any]:
        """Get user profile data
        
        Args:
            section: Optional section name, if None returns entire profile
            
        Returns:
            Dictionary of user profile data
        """
        if section:
            return self.user_profile.get(section, {})
        return self.user_profile
    
    def update_config(self, new_config: Dict[str, Any]) -> None:
        """Update the entire configuration
        
        Args:
            new_config: New configuration dictionary
        """
        try:
            self.config.update(new_config)
            self._save_json(self.config, self.config_path)
            logging.info("Configuration updated successfully")
        except Exception as e:
            logging.error(f"Error updating configuration: {e}")
            raise

    def update_user_profile(self, new_profile: Dict[str, Any] = None, section: str = None, key: str = None, value: Any = None) -> None:
        """Update user profile data
        
        Args:
            new_profile: Complete new profile dictionary (for bulk updates)
            section: Section name (for individual updates)
            key: Key to update (for individual updates)
            value: New value (for individual updates)
        """
        try:
            if new_profile is not None:
                # Bulk update - replace entire profile
                self.user_profile.update(new_profile)
                self._save_json(self.user_profile, self.user_profile_path)
                logging.info("User profile updated successfully (bulk update)")
            elif section and key is not None:
                # Individual update
                if section in self.user_profile:
                    self.user_profile[section][key] = value
                    self._save_json(self.user_profile, self.user_profile_path)
                    logging.info(f"Updated user profile: {section}.{key}")
                else:
                    logging.error(f"Section not found in user profile: {section}")
                    raise ValueError(f"Section not found in user profile: {section}")
            else:
                raise ValueError("Either provide new_profile for bulk update or section/key/value for individual update")
        except Exception as e:
            logging.error(f"Error updating user profile: {e}")
            raise
    
    def record_interaction(self, command_type: str, command_text: str, 
                          parameters: Dict[str, Any] = None) -> None:
        """Record a user interaction in the history
        
        Args:
            command_type: Type of command (e.g., 'file_operation', 'web_search')
            command_text: The text of the command
            parameters: Optional parameters for the command
        """
        # Create interaction record
        interaction = {
            "timestamp": datetime.now().isoformat(),
            "type": command_type,
            "text": command_text,
            "parameters": parameters or {}
        }
        
        # Add to interactions list
        self.user_profile["history"]["interactions"].append(interaction)
        
        # Update last commands
        self.user_profile["history"]["last_commands"].append(command_text)
        if len(self.user_profile["history"]["last_commands"]) > 10:
            self.user_profile["history"]["last_commands"] = self.user_profile["history"]["last_commands"][-10:]
        
        # Increment command count
        self.user_profile["history"]["total_commands"] += 1
        
        # Save the updated profile
        self._save_json(self.user_profile, self.user_profile_path)
        
    def update_session(self) -> None:
        """Update session information when starting a new session"""
        self.user_profile["personal"]["last_login"] = datetime.now().isoformat()
        self.user_profile["history"]["total_sessions"] += 1
        self._save_json(self.user_profile, self.user_profile_path)
        logging.info("Session information updated")
    
    def get_personalized_greeting(self) -> str:
        """Get a time-appropriate personalized greeting
        
        Returns:
            Greeting string with user's name
        """
        hour = datetime.now().hour
        
        if 5 <= hour < 12:
            time_of_day = "morning"
        elif 12 <= hour < 17:
            time_of_day = "afternoon"
        elif 17 <= hour < 22:
            time_of_day = "evening"
        else:
            time_of_day = "night"
        
        greeting = self.user_profile["preferences"]["greetings"][time_of_day]
        return greeting
