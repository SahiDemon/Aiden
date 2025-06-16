"""
Scheduled System Commands for Aiden AI
Handles scheduling of system commands with verification, modification, and abort capabilities
"""
import threading
import time
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import subprocess

class ScheduledSystemCommands:
    """Manages scheduled system commands with smart verification and control"""
    
    def __init__(self, voice_system=None, dashboard_backend=None):
        """Initialize the scheduled system commands manager
        
        Args:
            voice_system: Voice system for feedback
            dashboard_backend: Dashboard for UI updates
        """
        self.voice_system = voice_system
        self.dashboard_backend = dashboard_backend
        
        # Active schedules storage
        self.active_schedules = {}  # {task_id: task_info}
        self.schedule_counter = 0
        
        # Lock for thread safety
        self.schedule_lock = threading.Lock()
        
        logging.info("Scheduled system commands manager initialized")
    
    def process_system_command_request(self, command: str, operation: str, original_query: str) -> Dict[str, Any]:
        """Process a system command request with smart scheduling detection
        
        Args:
            command: The command string
            operation: Detected operation (shutdown, restart, etc.)
            original_query: Original user input
            
        Returns:
            Dictionary with processing result and next steps
        """
        # Check if this is a scheduled command
        time_info = self._extract_time_info(original_query)
        
        if time_info:
            # This is a scheduled command request
            return self._handle_scheduled_command(operation, time_info, original_query)
        
        # Check if this is a modification request
        if self._is_modification_request(original_query):
            return self._handle_modification_request(original_query)
        
        # Check if this is an abort request
        if self._is_abort_request(original_query):
            # Extract operation type from the query if specified
            operation_type = None
            query_lower = original_query.lower()
            if "shutdown" in query_lower:
                operation_type = "shutdown"
            elif "restart" in query_lower:
                operation_type = "restart"
            elif "sleep" in query_lower:
                operation_type = "sleep"
            elif "hibernate" in query_lower:
                operation_type = "hibernate"
            elif "lock" in query_lower:
                operation_type = "lock"
            
            # Call the existing abort_schedule method
            result = self.abort_schedule(operation_type)
            
            return {
                "action": "execute_immediate",
                "operation": "abort",
                "verified": True,
                "response": result.get("response", "Schedule cancelled.")
            }
        
        # This is an immediate command - ask for verification for dangerous commands
        if operation in ["shutdown", "restart"]:
            return self._request_immediate_verification(operation, original_query)
        
        # Safe commands (lock, sleep) can execute immediately
        return {
            "action": "execute_immediate",
            "operation": operation,
            "verified": True,
            "response": f"Executing {operation} command immediately."
        }
    
    def _extract_time_info(self, query: str) -> Optional[Dict[str, Any]]:
        """Extract time information from user query
        
        Args:
            query: User query string
            
        Returns:
            Dictionary with time info or None if no time found
        """
        query_lower = query.lower()
        
        # Common time patterns
        patterns = [
            (r"in (\d+) minutes?", "minutes"),
            (r"in (\d+) mins?", "minutes"), 
            (r"in (\d+) hours?", "hours"),
            (r"in (\d+) hrs?", "hours"),
            (r"in (\d+) seconds?", "seconds"),
            (r"in (\d+) secs?", "seconds"),
            (r"after (\d+) minutes?", "minutes"),
            (r"after (\d+) mins?", "minutes"),
        ]
        
        import re
        for pattern, unit in patterns:
            match = re.search(pattern, query_lower)
            if match:
                value = int(match.group(1))
                return {
                    "value": value,
                    "unit": unit,
                    "total_seconds": self._convert_to_seconds(value, unit)
                }
        
        return None
    
    def _convert_to_seconds(self, value: int, unit: str) -> int:
        """Convert time value to seconds"""
        if unit == "seconds":
            return value
        elif unit == "minutes":
            return value * 60
        elif unit == "hours":
            return value * 3600
        return 0
    
    def _handle_scheduled_command(self, operation: str, time_info: Dict[str, Any], original_query: str) -> Dict[str, Any]:
        """Handle a scheduled command request with verification
        
        Args:
            operation: Command operation (shutdown, restart, etc.)
            time_info: Time information extracted from query
            original_query: Original user input
            
        Returns:
            Processing result requiring user verification
        """
        # Calculate execution time
        execution_time = datetime.now() + timedelta(seconds=time_info["total_seconds"])
        
        # Create schedule info
        schedule_info = {
            "operation": operation,
            "time_info": time_info,
            "execution_time": execution_time,
            "original_query": original_query,
            "status": "pending_verification",
            "created_at": datetime.now()
        }
        
        return {
            "action": "request_verification",
            "schedule_info": schedule_info,
            "response": self._create_verification_message(operation, time_info),
            "verification_type": "schedule_dangerous_command"
        }
    
    def _create_verification_message(self, operation: str, time_info: Dict[str, Any]) -> str:
        """Create a verification message for the user"""
        action_phrases = {
            "shutdown": "shut down",
            "restart": "restart", 
            "sleep": "put to sleep",
            "hibernate": "hibernate",
            "lock": "lock"
        }
        
        action = action_phrases.get(operation, operation)
        time_str = f"{time_info['value']} {time_info['unit']}"
        
        return f"I'll {action} the computer in {time_str}, Boss."
    
    def confirm_schedule(self, schedule_info: Dict[str, Any]) -> Dict[str, Any]:
        """Confirm and activate a schedule using Python threads
        
        Args:
            schedule_info: Schedule information to confirm
            
        Returns:
            Result of schedule activation
        """
        with self.schedule_lock:
            # Generate unique task ID
            self.schedule_counter += 1
            task_id = f"task_{self.schedule_counter}"
            
            # Update schedule info
            schedule_info["task_id"] = task_id
            schedule_info["status"] = "active"
            
            # Store the schedule
            self.active_schedules[task_id] = schedule_info
            
            # Start the countdown thread
            countdown_thread = threading.Thread(
                target=self._execute_scheduled_command,
                args=(task_id,),
                daemon=True
            )
            countdown_thread.start()
            
            # Give the thread a moment to start, then update dashboard immediately to show details
            time.sleep(0.1)  # Small delay to ensure thread is running
            self._update_dashboard_schedules()
            
            operation = schedule_info["operation"]
            time_info = schedule_info["time_info"]
            time_str = f"{time_info['value']} {time_info['unit']}"
            
            action_phrases = {
                "shutdown": "shut down",
                "restart": "restart", 
                "sleep": "put to sleep",
                "hibernate": "hibernate",
                "lock": "lock"
            }
            
            action = action_phrases.get(operation, operation)
            response = f"Scheduled! I'll {action} the computer in {time_str}, Boss."
            
            return {
                "success": True,
                "task_id": task_id,
                "response": response
            }
    
    def _execute_scheduled_command(self, task_id: str):
        """Execute a scheduled command after countdown
        
        Args:
            task_id: ID of the task to execute
        """
        try:
            if task_id not in self.active_schedules:
                return
            
            schedule = self.active_schedules[task_id]
            total_seconds = schedule["time_info"]["total_seconds"]
            operation = schedule["operation"]
            
            # Countdown with smart updates to prevent dashboard spam
            remaining = total_seconds
            last_announcement = None
            last_dashboard_update = None
            
            # Initial dashboard update to show the schedule immediately
            self._update_dashboard_schedules()
            
            while remaining > 0 and task_id in self.active_schedules:
                # Announce at specific intervals
                if remaining <= 60 and remaining % 10 == 0:
                    if last_announcement != remaining:
                        self._announce_countdown(operation, remaining)
                        last_announcement = remaining
                elif remaining <= 300 and remaining % 60 == 0:  # Every minute for last 5 minutes
                    if last_announcement != remaining:
                        self._announce_countdown(operation, remaining)
                        last_announcement = remaining
                
                # Update dashboard at meaningful intervals
                should_update_dashboard = False
                
                # Update at 5 minutes (300 seconds)
                if remaining == 300 and last_dashboard_update != 300:
                    should_update_dashboard = True
                    last_dashboard_update = 300
                
                # Update at 1 minute (60 seconds)
                elif remaining == 60 and last_dashboard_update != 60:
                    should_update_dashboard = True
                    last_dashboard_update = 60
                
                # Update at 30 seconds for final countdown
                elif remaining == 30 and last_dashboard_update != 30:
                    should_update_dashboard = True
                    last_dashboard_update = 30
                
                if should_update_dashboard:
                    self._update_dashboard_schedules()
                
                time.sleep(1)
                remaining -= 1
            
            # Execute if not cancelled
            if task_id in self.active_schedules:
                self._execute_system_command(operation)
                
                # Clean up
                with self.schedule_lock:
                    if task_id in self.active_schedules:
                        del self.active_schedules[task_id]
                
                # Final dashboard update to remove completed task
                self._update_dashboard_schedules()
                
        except Exception as e:
            logging.error(f"Error executing scheduled command {task_id}: {e}")
            
            # Clean up on error
            with self.schedule_lock:
                if task_id in self.active_schedules:
                    del self.active_schedules[task_id]
            
            # Update dashboard to remove failed task
            self._update_dashboard_schedules()
    
    def _announce_countdown(self, operation: str, remaining_seconds: int):
        """Announce countdown to user"""
        if remaining_seconds >= 60:
            minutes = remaining_seconds // 60
            unit = "minute" if minutes == 1 else "minutes"
            message = f"{operation} in {minutes} {unit}"
        else:
            unit = "second" if remaining_seconds == 1 else "seconds"
            message = f"{operation} in {remaining_seconds} {unit}"
        
        if self.voice_system:
            self.voice_system.speak(message)
        
        logging.info(f"Countdown announcement: {message}")
    
    def _execute_system_command(self, operation: str):
        """Execute the actual system command
        
        Args:
            operation: Operation to execute
        """
        try:
            if operation == "shutdown":
                subprocess.run("shutdown /s /t 0", shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
            elif operation == "restart":
                subprocess.run("shutdown /r /t 0", shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
            elif operation == "sleep":
                subprocess.run("rundll32.exe powrprof.dll,SetSuspendState 0,1,0", shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
            elif operation == "hibernate":
                subprocess.run("shutdown /h", shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
            elif operation == "lock":
                subprocess.run("rundll32.exe user32.dll,LockWorkStation", shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
            
            logging.info(f"Executed scheduled system command: {operation}")
            
        except Exception as e:
            logging.error(f"Error executing system command {operation}: {e}")
    
    def modify_schedule_time(self, new_time_info: Dict[str, Any]) -> Dict[str, Any]:
        """Modify the time of an active schedule
        
        Args:
            new_time_info: New time information
            
        Returns:
            Result of modification
        """
        with self.schedule_lock:
            # Find the most recent active schedule (assume user wants to modify the latest)
            if not self.active_schedules:
                return {
                    "success": False,
                    "response": "No active schedules to modify."
                }
            
            # Get the most recent schedule
            latest_task = max(self.active_schedules.keys(), key=lambda k: self.active_schedules[k]["created_at"])
            schedule = self.active_schedules[latest_task]
            
            # Update the schedule
            old_time = schedule["time_info"]
            schedule["time_info"] = new_time_info
            schedule["execution_time"] = datetime.now() + timedelta(seconds=new_time_info["total_seconds"])
            
            operation = schedule["operation"]
            old_time_str = f"{old_time['value']} {old_time['unit']}"
            new_time_str = f"{new_time_info['value']} {new_time_info['unit']}"
            
            self._update_dashboard_schedules()
            
            return {
                "success": True,
                "response": f"Updated! Changed {operation} time from {old_time_str} to {new_time_str}."
            }
    
    def abort_schedule(self, operation_type: Optional[str] = None) -> Dict[str, Any]:
        """Abort active schedules
        
        Args:
            operation_type: Specific operation to abort, or None for all
            
        Returns:
            Result of abort operation
        """
        with self.schedule_lock:
            if not self.active_schedules:
                return {
                    "success": False,
                    "response": "No active schedules to cancel."
                }
            
            # If specific operation mentioned, cancel only that type
            if operation_type:
                cancelled = []
                to_remove = []
                
                for task_id, schedule in self.active_schedules.items():
                    if schedule["operation"] == operation_type:
                        cancelled.append(schedule["operation"])
                        to_remove.append(task_id)
                
                for task_id in to_remove:
                    del self.active_schedules[task_id]
                
                if cancelled:
                    # Update dashboard when schedules are cancelled
                    self._update_dashboard_schedules()
                    return {
                        "success": True,
                        "response": f"Cancelled {operation_type} schedule."
                    }
                else:
                    return {
                        "success": False,
                        "response": f"No active {operation_type} schedule found."
                    }
            
            # Cancel all schedules
            cancelled_operations = [s["operation"] for s in self.active_schedules.values()]
            self.active_schedules.clear()
            
            # Update dashboard when all schedules are cancelled
            self._update_dashboard_schedules()
            
            if len(cancelled_operations) == 1:
                return {
                    "success": True,
                    "response": f"Cancelled {cancelled_operations[0]} schedule."
                }
            else:
                ops_str = ", ".join(cancelled_operations)
                return {
                    "success": True,
                    "response": f"Cancelled all schedules: {ops_str}."
                }
    
    def _is_modification_request(self, query: str) -> bool:
        """Check if query is a modification request"""
        query_lower = query.lower()
        modification_keywords = [
            "change to", "change the time", "modify to", "update to",
            "make it", "instead of", "not", "actually"
        ]
        return any(keyword in query_lower for keyword in modification_keywords)
    
    def _is_abort_request(self, query: str) -> bool:
        """Check if query is an abort request"""
        query_lower = query.lower()
        abort_keywords = [
            "cancel", "abort", "stop", "don't", "never mind",
            "forget it", "cancel that", "abort that"
        ]
        return any(keyword in query_lower for keyword in abort_keywords)
    
    def _request_immediate_verification(self, operation: str, original_query: str) -> Dict[str, Any]:
        """Request verification for immediate dangerous commands"""
        action_phrases = {
            "shutdown": "shut down",
            "restart": "restart", 
            "sleep": "put to sleep",
            "hibernate": "hibernate",
            "lock": "lock"
        }
        
        action = action_phrases.get(operation, operation)
        
        return {
            "action": "request_verification",
            "operation": operation,
            "response": f"I'll {action} the computer now, Boss.",
            "verification_type": "immediate_dangerous_command"
        }
    
    def _update_dashboard_schedules(self):
        """Update dashboard with current schedules"""
        if not self.dashboard_backend:
            logging.debug("No dashboard backend available for schedule updates")
            return
        
        try:
            schedules_data = []
            
            for task_id, schedule in self.active_schedules.items():
                execution_time = schedule["execution_time"]
                remaining = (execution_time - datetime.now()).total_seconds()
                
                if remaining > 0:
                    schedule_data = {
                        "task_id": task_id,
                        "operation": schedule["operation"],
                        "remaining_seconds": int(remaining),
                        "execution_time": execution_time.strftime("%H:%M:%S"),
                        "original_query": schedule["original_query"]
                    }
                    schedules_data.append(schedule_data)
                    logging.debug(f"Added schedule to dashboard: {schedule['operation']} in {int(remaining)}s")
            
            # Only send action card if there are active schedules
            if schedules_data:
                action_card = {
                    "type": "scheduled_commands",
                    "title": "Active Scheduled Commands",
                    "schedules": schedules_data,
                    "actions": [
                        {"text": "Cancel All", "action": "cancel_all_schedules"},
                        {"text": "Modify Time", "action": "modify_schedule_time"}
                    ],
                    "status": "Active"
                }
                
                logging.debug(f"Sending dashboard action card with {len(schedules_data)} schedules")
                self.dashboard_backend._emit_ai_message(action_card, "action_card")
            else:
                logging.debug("No active schedules to display on dashboard")
            
        except Exception as e:
            logging.error(f"Error updating dashboard schedules: {e}")
    
    def get_active_schedules(self) -> List[Dict[str, Any]]:
        """Get list of active schedules for status checking"""
        with self.schedule_lock:
            return list(self.active_schedules.values())