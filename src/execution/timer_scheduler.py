"""
Timer Scheduler
Manage scheduled system commands with async task management
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Callable, Any, Awaitable
from uuid import UUID

from src.utils.logger import get_logger
from src.database.neon_client import get_db_client
from src.database.models import ScheduledTimer
from src.execution.system_controller import get_system_controller
from src.utils.websocket_broadcast import broadcast_message

logger = get_logger(__name__)


class TimerScheduler:
    """Async scheduler for persisted delayed commands and legacy power timers."""
    
    def __init__(self):
        self.active_tasks: Dict[str, asyncio.Task] = {}
        self.system_controller = get_system_controller()
        self._shutdown = False
        self._command_executor: Optional[Callable[[Dict[str, Any], Optional[str]], Awaitable[Dict[str, Any]]]] = None
        
        # Action mappings
        self.action_handlers = {
            "shutdown": self.system_controller.shutdown,
            "restart": self.system_controller.restart,
            "sleep": self.system_controller.sleep,
            "hibernate": self.system_controller.hibernate,
            "lock": self.system_controller.lock_screen
        }

    def set_command_executor(
        self,
        executor: Callable[[Dict[str, Any], Optional[str]], Awaitable[Dict[str, Any]]],
    ) -> None:
        """Provide the normal command path used by delayed non-power actions."""
        self._command_executor = executor
    
    async def start(self):
        """Start the timer scheduler and restore active timers"""
        logger.info("Starting timer scheduler...")
        
        # Restore active timers from database
        await self._restore_active_timers()
        
        logger.info(f"Timer scheduler started with {len(self.active_tasks)} active timers")
    
    async def stop(self):
        """Stop the timer scheduler and cancel all tasks"""
        logger.info("Stopping timer scheduler...")
        self._shutdown = True
        
        # Cancel all active tasks
        for timer_id, task in self.active_tasks.items():
            if not task.done():
                task.cancel()
                logger.info(f"Cancelled timer task: {timer_id}")
        
        # Wait for tasks to complete
        if self.active_tasks:
            await asyncio.gather(*self.active_tasks.values(), return_exceptions=True)
        
        self.active_tasks.clear()
        logger.info("Timer scheduler stopped")
    
    async def create_timer(
        self,
        action: str,
        duration_seconds: int,
        user_id: str = "default",
        conversation_id: Optional[str] = None,
        command_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[ScheduledTimer]:
        """
        Create a new timer
        
        Args:
            action: Human-readable action identifier used for cancellation/UI.
            duration_seconds: Delay in seconds
            user_id: User ID
            conversation_id: Optional conversation ID
            
        Returns:
            Created timer or None if failed
        """
        if command_data is None and action not in self.action_handlers:
            logger.error(f"Unknown action: {action}")
            return None

        if command_data is not None and not command_data.get("type"):
            logger.error("Scheduled command has no command type")
            return None
        
        if duration_seconds <= 0:
            logger.error(f"Invalid duration: {duration_seconds}")
            return None
        
        # Calculate scheduled time
        scheduled_time = datetime.utcnow() + timedelta(seconds=duration_seconds)
        
        # Save to database
        db_client = await get_db_client()
        timer = await db_client.create_timer(
            action=action,
            scheduled_time=scheduled_time,
            duration_seconds=duration_seconds,
            user_id=user_id,
            conversation_id=conversation_id,
            command_data=command_data,
        )
        
        if not timer:
            logger.error("Failed to create timer in database")
            return None
        
        # Schedule the task
        await self._schedule_timer_task(timer)
        
        # Broadcast update
        await self._broadcast_timer_update()
        await self._broadcast_timer_event(
            timer,
            "scheduled",
            f"Scheduled {self._describe_timer(timer)}.",
        )
        
        logger.info(f"Created timer: {action} in {duration_seconds}s (ID: {timer.id})")
        return timer
    
    async def cancel_timer(self, timer_id: str) -> bool:
        """Cancel a timer by ID"""
        # Cancel the task
        if timer_id in self.active_tasks:
            task = self.active_tasks[timer_id]
            if not task.done():
                task.cancel()
            del self.active_tasks[timer_id]
        
        # Update database
        db_client = await get_db_client()
        success = await db_client.cancel_timer(timer_id)
        
        if success:
            logger.info(f"Cancelled timer: {timer_id}")
            await self._broadcast_timer_update()
        
        return success
    
    async def cancel_timers_by_action(self, action: str, user_id: str = "default") -> int:
        """Cancel all active timers for a specific action"""
        # Get timers to cancel
        db_client = await get_db_client()
        count = await db_client.cancel_timers_by_action(action, user_id)
        
        # Cancel tasks
        cancelled_tasks = []
        for timer_id, task in list(self.active_tasks.items()):
            timer = await db_client.get_timer_by_id(timer_id)
            if timer and timer.action == action and timer.user_id == user_id:
                if not task.done():
                    task.cancel()
                cancelled_tasks.append(timer_id)
        
        # Remove cancelled tasks
        for timer_id in cancelled_tasks:
            del self.active_tasks[timer_id]
        
        if count > 0:
            logger.info(f"Cancelled {count} {action} timers")
            await self._broadcast_timer_update()
        
        return count
    
    async def cancel_all_timers(self, user_id: str = "default") -> int:
        """Cancel all active timers for a user"""
        db_client = await get_db_client()
        timers = await db_client.get_active_timers(user_id)
        count = 0
        
        for timer in timers:
            success = await self.cancel_timer(str(timer.id))
            if success:
                count += 1
        
        logger.info(f"Cancelled all {count} active timers for user {user_id}")
        if count > 0:
            await self._broadcast_timer_update()
        
        return count
    
    async def get_active_timers(self, user_id: str = "default") -> List[Dict]:
        """Get all active timers for a user with remaining time"""
        db_client = await get_db_client()
        timers = await db_client.get_active_timers(user_id)
        
        result = []
        for timer in timers:
            timer_dict = timer.to_dict()
            timer_dict['remaining_seconds'] = timer.remaining_seconds
            result.append(timer_dict)
        
        return result
    
    async def _restore_active_timers(self):
        """Restore active timers from database on startup"""
        try:
            db_client = await get_db_client()
            timers = await db_client.get_active_timers()
            
            for timer in timers:
                # Check if timer has already expired
                if timer.remaining_seconds <= 0:
                    # Mark as completed or execute immediately
                    await db_client.complete_timer(str(timer.id), "Expired during downtime")
                    continue
                
                # Schedule the timer
                await self._schedule_timer_task(timer)
            
            logger.info(f"Restored {len(self.active_tasks)} active timers")
            
        except Exception as e:
            logger.error(f"Error restoring timers: {e}")
    
    async def _schedule_timer_task(self, timer: ScheduledTimer):
        """Schedule an async task for a timer"""
        if str(timer.id) in self.active_tasks:
            logger.warning(f"Timer {timer.id} already scheduled")
            return
        
        # Create and start the task
        task = asyncio.create_task(self._execute_timer(timer))
        self.active_tasks[str(timer.id)] = task
    
    async def _execute_timer(self, timer: ScheduledTimer):
        """Execute a timer task"""
        try:
            # Calculate remaining time
            remaining = timer.remaining_seconds
            
            if remaining <= 0:
                logger.warning(f"Timer {timer.id} already expired")
                return
            
            logger.info(f"Timer {timer.id} will execute {timer.action} in {remaining}s")
            
            # Wait for the scheduled time
            await asyncio.sleep(remaining)
            
            # Check if cancelled during sleep
            if self._shutdown:
                return
            
            await self._broadcast_timer_event(timer, "fired", f"Running scheduled {self._describe_timer(timer)}.")
            success, error_msg = await self._run_timer_action(timer)
            await self._complete_timer(timer, error_msg if not success else None)
            if success:
                logger.info(f"Timer {timer.id} executed successfully: {timer.action}")
                await self._broadcast_timer_event(timer, "completed", f"Completed scheduled {self._describe_timer(timer)}.")
            else:
                logger.error(error_msg)
                await self._broadcast_timer_event(timer, "failed", f"Scheduled {self._describe_timer(timer)} failed.")
        
        except asyncio.CancelledError:
            logger.info(f"Timer {timer.id} was cancelled")
        except Exception as e:
            error_msg = f"Unexpected error in timer {timer.id}: {str(e)}"
            logger.error(error_msg)
            await self._complete_timer(timer, error_msg)
        finally:
            # Clean up task
            timer_id = str(timer.id)
            if timer_id in self.active_tasks:
                del self.active_tasks[timer_id]
            
            # Broadcast update
            await self._broadcast_timer_update()
    
    async def _complete_timer(self, timer: ScheduledTimer, error_message: Optional[str] = None):
        """Mark timer as completed in database"""
        try:
            db_client = await get_db_client()
            await db_client.complete_timer(str(timer.id), error_message)
        except Exception as e:
            logger.error(f"Error completing timer {timer.id}: {e}")

    async def _run_timer_action(self, timer: ScheduledTimer) -> tuple[bool, Optional[str]]:
        """Run one timer through either the legacy handler or command executor."""
        command_data = timer.command_data
        try:
            if command_data:
                if not self._command_executor:
                    # Timers restored on startup may become due before the
                    # first interactive command initializes the executor.
                    from src.execution.command_executor import get_command_executor
                    self.set_command_executor(get_command_executor().execute)
                result = await self._command_executor(command_data, timer.conversation_id)
                if result.get("success"):
                    return True, None
                response_data = result.get("response_data")
                detail = (
                    response_data.get("message")
                    if isinstance(response_data, dict)
                    else None
                )
                return False, detail or result.get("error") or f"Scheduled {timer.action} action failed"

            handler = self.action_handlers.get(timer.action)
            if not handler:
                return False, f"Unknown action: {timer.action}"
            success = await handler()
            return success, None if success else f"Action {timer.action} failed"
        except Exception as exc:
            return False, f"Error executing {timer.action}: {exc}"

    @staticmethod
    def _describe_timer(timer: ScheduledTimer) -> str:
        command = timer.command_data or {}
        command_type = command.get("type") or timer.action
        params = command.get("params") or {}
        action = params.get("action") or params.get("operation") or params.get("target")
        return f"{command_type.replace('_', ' ')}{f' ({action})' if action else ''}"

    async def _broadcast_timer_event(self, timer: ScheduledTimer, event: str, message: str) -> None:
        """Notify connected clients when a delayed command changes lifecycle state."""
        payload = {"event": event, "timer": timer.to_dict(), "message": message}
        try:
            await broadcast_message("timer_event", payload)
            await broadcast_message(
                "message",
                {"role": "assistant", "content": message, "timestamp": datetime.now().isoformat()},
            )
        except Exception as exc:
            logger.error(f"Error broadcasting timer event: {exc}")
    
    async def _broadcast_timer_update(self):
        """Broadcast timer updates to connected clients"""
        try:
            timers = await self.get_active_timers()
            await broadcast_message("timer_update", {"timers": timers})
        except Exception as e:
            logger.error(f"Error broadcasting timer update: {e}")


# Global instance
_timer_scheduler: Optional[TimerScheduler] = None


async def get_timer_scheduler() -> TimerScheduler:
    """Get or create global timer scheduler"""
    global _timer_scheduler
    if _timer_scheduler is None:
        _timer_scheduler = TimerScheduler()
        await _timer_scheduler.start()
    return _timer_scheduler


async def stop_timer_scheduler():
    """Stop global timer scheduler"""
    global _timer_scheduler
    if _timer_scheduler:
        await _timer_scheduler.stop()
        _timer_scheduler = None
