"""
Timer Scheduler
Manage scheduled system commands with async task management
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Callable
from uuid import UUID

from src.utils.logger import get_logger
from src.database.neon_client import get_db_client
from src.database.models import ScheduledTimer
from src.execution.system_controller import get_system_controller
from src.utils.websocket_broadcast import broadcast_message

logger = get_logger(__name__)


class TimerScheduler:
    """Async timer scheduler for system commands"""
    
    def __init__(self):
        self.active_tasks: Dict[str, asyncio.Task] = {}
        self.system_controller = get_system_controller()
        self._shutdown = False
        
        # Action mappings
        self.action_handlers = {
            "shutdown": self.system_controller.shutdown,
            "restart": self.system_controller.restart,
            "sleep": self.system_controller.sleep,
            "hibernate": self.system_controller.hibernate,
            "lock": self.system_controller.lock_screen
        }
    
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
        conversation_id: Optional[str] = None
    ) -> Optional[ScheduledTimer]:
        """
        Create a new timer
        
        Args:
            action: Action to perform (shutdown, hibernate, etc.)
            duration_seconds: Delay in seconds
            user_id: User ID
            conversation_id: Optional conversation ID
            
        Returns:
            Created timer or None if failed
        """
        if action not in self.action_handlers:
            logger.error(f"Unknown action: {action}")
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
            conversation_id=conversation_id
        )
        
        if not timer:
            logger.error("Failed to create timer in database")
            return None
        
        # Schedule the task
        await self._schedule_timer_task(timer)
        
        # Broadcast update
        await self._broadcast_timer_update()
        
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
            
            # Execute the action
            handler = self.action_handlers.get(timer.action)
            if not handler:
                error_msg = f"Unknown action: {timer.action}"
                logger.error(error_msg)
                await self._complete_timer(timer, error_msg)
                return
            
            logger.info(f"Executing timer action: {timer.action}")
            
            try:
                success = await handler()
                if success:
                    await self._complete_timer(timer)
                    logger.info(f"Timer {timer.id} executed successfully: {timer.action}")
                else:
                    error_msg = f"Action {timer.action} failed"
                    await self._complete_timer(timer, error_msg)
                    logger.error(error_msg)
            except Exception as e:
                error_msg = f"Error executing {timer.action}: {str(e)}"
                await self._complete_timer(timer, error_msg)
                logger.error(error_msg)
        
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