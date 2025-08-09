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
        
        # Check if user mentioned scheduling but didn't specify complete time
        if self._is_incomplete_schedule_request(original_query) and not time_info:
            return self._handle_incomplete_schedule_request(operation, original_query)
        
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
        
        # This is an immediate command - ask for verification for ALL system commands
        return self._request_immediate_verification(operation, original_query)
    
    def _extract_time_info(self, query: str) -> Optional[Dict[str, Any]]:
        """Extract time information from user query
        
        Args:
            query: User query string
            
        Returns:
            Dictionary with time info or None if no time found
        """
        query_lower = query.lower()
        
        # Common time patterns - more comprehensive
        patterns = [
            (r"in (\d+) minutes?", "minutes"),
            (r"in (\d+) mins?", "minutes"), 
            (r"in (\d+) min\b", "minutes"),  # Added pattern for "min" without 's'
            (r"in (\d+) hours?", "hours"),
            (r"in (\d+) hrs?", "hours"),
            (r"in (\d+) hr\b", "hours"),  # Added pattern for "hr" without 's'
            (r"in (\d+) seconds?", "seconds"),
            (r"in (\d+) secs?", "seconds"),
            (r"in (\d+) sec\b", "seconds"),  # Added pattern for "sec" without 's'
            (r"after (\d+) minutes?", "minutes"),
            (r"after (\d+) mins?", "minutes"),
            (r"after (\d+) min\b", "minutes"),  # Added pattern for "min" without 's'
            (r"(\d+) minutes? from now", "minutes"),  # Added "from now" pattern
            (r"(\d+) mins? from now", "minutes"),
            (r"(\d+) min from now", "minutes"),
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
        
        # Execute scheduled commands directly without verification
        schedule_id = f"{operation}_{int(execution_time.timestamp())}"
        self.scheduled_tasks[schedule_id] = schedule_info
        
        # Start the scheduled task
        self._start_scheduled_task(schedule_id, schedule_info)
        
        return {
            "action": "execute_schedule",
            "schedule_info": schedule_info,
            "response": self._create_confirmation_message(operation, time_info),
            "schedule_id": schedule_id
        }
    
    def _create_confirmation_message(self, operation: str, time_info: Dict[str, Any]) -> str:
        """Create a confirmation message for scheduled commands"""
        action_phrases = {
            "shutdown": "shut down",
            "restart": "restart",
            "sleep": "put to sleep", 
            "hibernate": "hibernate",
            "lock": "lock"
        }
        
        action = action_phrases.get(operation, operation)
        time_str = f"{time_info['value']} {time_info['unit']}"
        
        return f"I'll {action} the computer in {time_str}. The schedule is now active."
    
    def _start_scheduled_task(self, schedule_id: str, schedule_info: Dict[str, Any]) -> None:
        """Start a scheduled task timer"""
        import threading
        
        execution_time = schedule_info["execution_time"]
        delay = (execution_time - datetime.now()).total_seconds()
        
        if delay > 0:
            # Update status to active
            schedule_info["status"] = "active"
            self.active_schedules[schedule_id] = schedule_info
            
            # Start timer thread
            timer = threading.Timer(delay, self._execute_scheduled_command, args=[schedule_id])
            timer.daemon = True
            timer.start()
            
            # Update dashboard
            self._update_dashboard_schedules()
            
            logging.info(f"Scheduled {schedule_info['operation']} to execute in {delay:.1f} seconds")
        else:
            # Execute immediately if time has passed
            self._execute_scheduled_command(schedule_id)
    
    def _execute_scheduled_command(self, schedule_id: str) -> None:
        """Execute a scheduled command"""
        if schedule_id not in self.active_schedules:
            return
            
        schedule_info = self.active_schedules[schedule_id]
        operation = schedule_info["operation"]
        
        try:
            # Execute the system command
            if operation == "shutdown":
                subprocess.run(["shutdown", "/s", "/t", "0"], check=True)
            elif operation == "restart":
                subprocess.run(["shutdown", "/r", "/t", "0"], check=True)
            elif operation == "sleep":
                subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], check=True)
            elif operation == "hibernate":
                subprocess.run(["shutdown", "/h"], check=True)
            elif operation == "lock":
                subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], check=True)
                
            logging.info(f"Successfully executed scheduled {operation}")
            
        except Exception as e:
            logging.error(f"Failed to execute scheduled {operation}: {e}")
        finally:
            # Clean up
            if schedule_id in self.active_schedules:
                del self.active_schedules[schedule_id]
            if schedule_id in self.scheduled_tasks:
                del self.scheduled_tasks[schedule_id]
            self._update_dashboard_schedules()
    
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
            
            # Update dashboard immediately before starting thread
            self._update_dashboard_schedules()
            
            # Start the countdown thread
            countdown_thread = threading.Thread(
                target=self._execute_scheduled_command,
                args=(task_id,),
                daemon=True
            )
            countdown_thread.start()
            
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
            
            # Log for debugging
            logging.info(f"Schedule confirmed: {operation} in {time_str} (Task ID: {task_id})")
            
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
            
            # Countdown with minimal voice announcements and smart dashboard updates
            remaining = total_seconds
            last_announcement = None
            last_dashboard_update = 0
            
            # Initial dashboard update to show the schedule immediately
            self._update_dashboard_schedules()
            
            while remaining > 0 and task_id in self.active_schedules:
                # Only announce at 5 minutes and 1 minute
                if remaining == 300 and last_announcement != 300:  # 5 minutes
                    self._announce_countdown(operation, remaining)
                    last_announcement = 300
                elif remaining == 60 and last_announcement != 60:  # 1 minute
                    self._announce_countdown(operation, remaining)
                    last_announcement = 60
                
                # Update dashboard every 10 seconds during final minute, every 30 seconds otherwise
                should_update_dashboard = False
                
                if remaining <= 60:
                    # Final minute - update every 10 seconds
                    if remaining % 10 == 0 and last_dashboard_update != remaining:
                        should_update_dashboard = True
                        last_dashboard_update = remaining
                elif remaining <= 300:
                    # Final 5 minutes - update every 30 seconds
                    if remaining % 30 == 0 and last_dashboard_update != remaining:
                        should_update_dashboard = True
                        last_dashboard_update = remaining
                else:
                    # Beyond 5 minutes - update every 60 seconds
                    if remaining % 60 == 0 and last_dashboard_update != remaining:
                        should_update_dashboard = True
                        last_dashboard_update = remaining
                
                if should_update_dashboard:
                    self._update_dashboard_schedules()
                
                # Sleep for 1 second
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
                ops_str = ", ".join(set(cancelled_operations))
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
            "cancel", "abort", "stop", "don't", "never mind", "do not",
            "forget it", "cancel that", "abort that", "cancel the", "stop the",
            "terminate", "end", "halt", "kill"
        ]
        return any(keyword in query_lower for keyword in abort_keywords)
    
    def _request_immediate_verification(self, operation: str, original_query: str) -> Dict[str, Any]:
        """Execute immediate commands directly without verification"""
        action_phrases = {
            "shutdown": "shut down",
            "restart": "restart", 
            "sleep": "put to sleep",
            "hibernate": "hibernate",
            "lock": "lock"
        }
        
        action = action_phrases.get(operation, operation)
        
        return {
            "action": "execute_immediate",
            "operation": operation,
            "verified": True,
            "response": f"I'll {action} the computer now, Boss."
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
                        "remaining_seconds": max(1, int(remaining)),  # Ensure at least 1 second
                        "execution_time": execution_time.strftime("%H:%M:%S"),
                        "original_query": schedule["original_query"]
                    }
                    schedules_data.append(schedule_data)
                    logging.debug(f"Added schedule to dashboard: {schedule['operation']} in {int(remaining)}s")
                else:
                    # Remove expired schedules
                    logging.debug(f"Removing expired schedule: {task_id}")
            
            # Use a consistent message ID to update the same card instead of creating new ones
            action_card = {
                "type": "scheduled_commands",
                "title": "Active Scheduled Commands",
                "schedules": schedules_data,
                "actions": [
                    {"text": "Cancel All", "action": "cancel_all_schedules"},
                    {"text": "Modify Time", "action": "modify_schedule_time"}
                ],
                "status": "Active" if schedules_data else "Empty",
                "message_id": "system_schedules_card",  # Unique ID to prevent duplicates
                "update_existing": True  # Flag to update existing card
            }
            
            logging.info(f"Updating dashboard with {len(schedules_data)} active schedules")
            self.dashboard_backend._emit_ai_message(action_card, "action_card")
            
        except Exception as e:
            logging.error(f"Error updating dashboard schedules: {e}")
            import traceback
            traceback.print_exc()
    
    def get_active_schedules(self) -> List[Dict[str, Any]]:
        """Get list of active schedules for status checking"""
        with self.schedule_lock:
            return list(self.active_schedules.values())
    
    def _is_incomplete_schedule_request(self, query: str) -> bool:
        """Check if query mentions scheduling but is incomplete
        
        Args:
            query: User query string
            
        Returns:
            True if this appears to be an incomplete schedule request
        """
        query_lower = query.lower().strip()
        
        # Explicit incomplete patterns - these are DEFINITELY incomplete
        explicit_incomplete_patterns = [
            "can you schedule",
            "schedule a",
            "schedule the", 
            "scheduler",
            "i want to schedule",
            "please schedule",
            "schedule something"
        ]
        
        # Check for explicit incomplete patterns first
        for pattern in explicit_incomplete_patterns:
            if pattern in query_lower:
                return True
        
        # Look for scheduling indicators
        schedule_indicators = [
            "schedule", "scheduler", "in", "after", "delay"
        ]
        
        # Look for incomplete time patterns
        incomplete_patterns = [
            r"\bin\s*$",  # ends with "in"
            r"\bafter\s*$",  # ends with "after"
            r"\bschedul\w*\s+\w+\s+in\s*$",  # "schedule something in"
            r"\bschedul\w*\s+\w+\s+after\s*$",  # "schedule something after"
        ]
        
        import re
        
        # Check if it has scheduling indicators
        has_schedule_indicator = any(indicator in query_lower for indicator in schedule_indicators)
        
        # Check if it matches incomplete patterns
        has_incomplete_pattern = any(re.search(pattern, query_lower) for pattern in incomplete_patterns)
        
        return has_schedule_indicator and (has_incomplete_pattern or 
                                         (("in" in query_lower or "after" in query_lower) and 
                                          not self._extract_time_info(query)))
    
    def _handle_incomplete_schedule_request(self, operation: str, original_query: str) -> Dict[str, Any]:
        """Handle incomplete schedule request by asking for time
        
        Args:
            operation: The operation to schedule
            original_query: Original user input
            
        Returns:
            Processing result asking for time specification
        """
        action_phrases = {
            "shutdown": "shut down",
            "restart": "restart", 
            "sleep": "put to sleep",
            "hibernate": "hibernate",
            "lock": "lock"
        }
        
        action = action_phrases.get(operation, operation)
        
        return {
            "action": "request_time_specification",
            "operation": operation,
            "original_query": original_query,
            "response": f"I'll {action} the computer. How long from now? For example, say '10 minutes' or '1 hour'.",
            "verification_type": "time_specification_needed"
        }