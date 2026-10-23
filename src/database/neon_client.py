"""
Neon DB Client
Async PostgreSQL database client using SQLAlchemy
"""
import asyncio
import logging
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.future import select
from sqlalchemy import text, func
from sqlalchemy.exc import IntegrityError

# CRITICAL: Import event loop policy FIRST
from src.utils.event_loop import ensure_selector_event_loop
from src.database.models import Base, Conversation, Message, CommandHistory, UserPreferences, ScheduledTimer
from src.utils.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class NeonDBClient:
    """Async Neon DB client for PostgreSQL operations"""
    
    def __init__(self):
        self.settings = get_settings()
        self.engine = None
        self.session_maker = None
        self.next_reconnect_at = 0.0
        
    async def connect(self):
        """Initialize database connection"""
        try:
            db_url = self._build_asyncpg_url(self.settings.database.database_url)
            
            # asyncpg connection arguments (pure async driver, works on Windows)
            connect_args = {
                "timeout": 60,  # Neon can take a moment to wake up / pool
                "command_timeout": 60,
                "ssl": True,  # Force SSL
            }

            if "pooler." in db_url or "pooler-" in db_url:
                # Pooler endpoints can benefit from a smaller statement cache.
                connect_args["statement_cache_size"] = 0
            
            logger.info("Creating Neon DB engine with asyncpg (native async)...")
            from sqlalchemy.pool import AsyncAdaptedQueuePool
            
            self.engine = create_async_engine(
                db_url,
                poolclass=AsyncAdaptedQueuePool,
                pool_size=3,
                max_overflow=5,
                pool_pre_ping=True,
                pool_recycle=300,
                echo=False,  # Keep console clean; avoid verbose raw SQL dump
                connect_args=connect_args
            )
            
            # Create session maker
            self.session_maker = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            logger.info("Testing Neon DB connection...")
            # Test connection with timeout
            try:
                await asyncio.wait_for(self._test_connection(), timeout=60)
            except Exception as test_error:
                logger.error(
                    "Connection test failed: %s (%s)",
                    test_error,
                    type(test_error).__name__,
                )
                raise
            
            logger.info("Connected to Neon DB successfully!")
            self.next_reconnect_at = 0.0
            
        except asyncio.TimeoutError:
            logger.error("Neon DB connection timed out")
            logger.warning("Database features will be unavailable, but Aiden will continue running")
            await self._reset_failed_connection()
        except Exception as e:
            logger.error(f"Failed to connect to Neon DB: {e}")
            logger.warning("Database features will be unavailable, but Aiden will continue running")
            # Don't raise - allow app to continue without database
            await self._reset_failed_connection()

    async def _reset_failed_connection(self) -> None:
        """Release a failed engine and space out later connection attempts."""
        engine = self.engine
        self.engine = None
        self.session_maker = None
        self.next_reconnect_at = time.monotonic() + 30
        if engine is not None:
            try:
                await engine.dispose()
            except Exception as exc:
                logger.warning("Could not dispose failed Neon DB engine: %s", exc)

    def _build_asyncpg_url(self, raw_url: str) -> str:
        """Normalize Neon connection strings for asyncpg."""
        if not raw_url:
            return raw_url

        normalized = raw_url.strip()
        if normalized.startswith("postgresql://"):
            normalized = normalized.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif normalized.startswith("postgres://"):
            normalized = normalized.replace("postgres://", "postgresql+asyncpg://", 1)
        elif not normalized.startswith("postgresql+asyncpg://"):
            normalized = f"postgresql+asyncpg://{normalized}"

        parts = urlsplit(normalized)
        query_params = []
        for key, value in parse_qsl(parts.query, keep_blank_values=True):
            if key.lower() in {"sslmode", "channel_binding"}:
                continue
            query_params.append((key, value))

        # asyncpg does not use sslmode; it uses the connection argument.
        query = urlencode(query_params)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))

    async def _test_connection(self) -> None:
        """Run a simple query to verify the connection is usable."""
        if not self.engine:
            raise RuntimeError("Database engine not initialized")

        async with self.engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            result.close()
    
    async def disconnect(self):
        """Close database connection"""
        if self.engine:
            await self.engine.dispose()
            logger.info("Disconnected from Neon DB")
    
    async def create_tables(self):
        """Create tables and apply the small backwards-compatible timer migration."""
        if not self.engine:
            logger.warning("Database not connected - skipping table creation")
            return
            
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                # ``create_all`` deliberately does not alter existing tables.
                # Older installations have scheduled_timers without this column,
                # so add it in-place before the scheduler tries to load timers.
                await conn.execute(text(
                    "ALTER TABLE scheduled_timers "
                    "ADD COLUMN IF NOT EXISTS command_data JSONB"
                ))
            logger.info("Database tables created/verified")
        except Exception as e:
            logger.error(f"Error creating tables: {e}")
            logger.warning("Continuing without database tables")
    
    @asynccontextmanager
    async def session(self):
        """Get database session context manager"""
        if not self.session_maker:
            logger.warning("Database not connected - skipping operation")
            yield None
            return
            
        async with self.session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    
    # Conversation operations
    async def create_conversation(
        self,
        user_id: str = "default",
        mode: str = "voice",
        conversation_id: Optional[str] = None
    ) -> Optional[Conversation]:
        """Create new conversation"""
        async with self.session() as session:
            if not session:
                return None
            conversation = Conversation(
                id=conversation_id,
                user_id=user_id,
                mode=mode
            )
            session.add(conversation)
            await session.flush()
            await session.refresh(conversation)
            return conversation

    async def ensure_conversation_exists(
        self,
        conversation_id: str,
        user_id: str = "default",
        mode: str = "voice"
    ) -> bool:
        """Ensure a specific conversation row exists before inserting messages."""
        async with self.session() as session:
            if not session:
                return False

            result = await session.execute(
                select(Conversation).where(Conversation.id == conversation_id)
            )
            conversation = result.scalar_one_or_none()
            if conversation:
                return True

            conversation = Conversation(
                id=conversation_id,
                user_id=user_id,
                mode=mode
            )
            session.add(conversation)
            try:
                await session.flush()
            except IntegrityError:
                # Another task created the same conversation concurrently.
                await session.rollback()
            return True

    async def end_conversation(self, conversation_id: str):
        """Mark conversation as ended"""
        async with self.session() as session:
            result = await session.execute(
                select(Conversation).where(Conversation.id == conversation_id)
            )
            conversation = result.scalar_one_or_none()
            if conversation:
                from datetime import datetime
                conversation.ended_at = datetime.utcnow()

    async def get_active_conversation(self, user_id: str = "default") -> Optional[Conversation]:
        """Get active (not ended) conversation for user"""
        async with self.session() as session:
            result = await session.execute(
                select(Conversation)
                .where(Conversation.user_id == user_id)
                .where(Conversation.ended_at == None)
                .order_by(Conversation.created_at.desc())
            )
            return result.scalar_one_or_none()

    async def count_conversations(self) -> int:
        """Get total number of conversations."""
        async with self.session() as session:
            result = await session.execute(select(func.count(Conversation.id)))
            return result.scalar() or 0

    async def count_commands(self) -> int:
        """Get total number of commands."""
        async with self.session() as session:
            result = await session.execute(select(func.count(CommandHistory.id)))
            return result.scalar() or 0

    async def get_conversations(self, limit: int = 50) -> List[Conversation]:
        """Get list of conversations."""
        async with self.session() as session:
            result = await session.execute(
                select(Conversation).order_by(Conversation.created_at.desc()).limit(limit)
            )
            return result.scalars().all()

    async def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Get conversation by ID."""
        async with self.session() as session:
            result = await session.execute(
                select(Conversation).where(Conversation.id == conversation_id)
            )
            return result.scalar_one_or_none()

    async def delete_conversation(self, conversation_id: str) -> None:
        """Delete a conversation by ID."""
        async with self.session() as session:
            conv = await session.get(Conversation, conversation_id)
            if conv:
                await session.delete(conv)

    # Message operations
    async def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[Message]:
        """Add message to conversation"""
        async with self.session() as session:
            if not session:
                return None
            message = Message(
                conversation_id=conversation_id,
                role=role,
                content=content,
                extra_data=metadata or {}
            )
            session.add(message)
            await session.flush()
            await session.refresh(message)
            return message

    async def get_conversation_messages(
        self,
        conversation_id: str,
        limit: Optional[int] = None
    ) -> List[Message]:
        """Get messages from conversation"""
        async with self.session() as session:
            query = (
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.timestamp.asc())
            )
            if limit:
                query = query.limit(limit)
            result = await session.execute(query)
            return result.scalars().all()
    
    async def get_recent_messages(
        self,
        user_id: str = "default",
        limit: int = 50
    ) -> List[Message]:
        """Get recent messages across all conversations"""
        async with self.session() as session:
            result = await session.execute(
                select(Message)
                .join(Conversation)
                .where(Conversation.user_id == user_id)
                .order_by(Message.timestamp.desc())
                .limit(limit)
            )
            return result.scalars().all()
    
    # Command history operations
    async def log_command(
        self,
        command_type: str,
        command_data: Dict[str, Any],
        success: bool,
        error_message: Optional[str] = None,
        execution_time_ms: Optional[int] = None,
        conversation_id: Optional[str] = None
    ) -> Optional[CommandHistory]:
        """Log executed command"""
        async with self.session() as session:
            if not session:
                return None
            command = CommandHistory(
                conversation_id=conversation_id,
                command_type=command_type,
                command_data=command_data,
                success=success,
                error_message=error_message,
                execution_time_ms=execution_time_ms
            )
            session.add(command)
            await session.flush()
            # INSERT RETURNING populates the ID; defaults are populated by
            # flush. Avoid a redundant remote SELECT before the awaited commit.
            return command
    
    async def get_command_history(
        self,
        limit: int = 100,
        command_type: Optional[str] = None
    ) -> List[CommandHistory]:
        """Get command execution history"""
        async with self.session() as session:
            query = select(CommandHistory).order_by(CommandHistory.executed_at.desc()).limit(limit)
            if command_type:
                query = query.where(CommandHistory.command_type == command_type)
            result = await session.execute(query)
            return result.scalars().all()
    
    # User preferences operations
    async def get_user_preferences(self, user_id: str = "default") -> Optional[UserPreferences]:
        """Get user preferences"""
        async with self.session() as session:
            if not session:
                return None
            result = await session.execute(
                select(UserPreferences).where(UserPreferences.user_id == user_id)
            )
            return result.scalar_one_or_none()
    
    async def update_user_preferences(
        self,
        user_id: str = "default",
        settings: Dict[str, Any] = None
    ) -> UserPreferences:
        """Update or create user preferences"""
        async with self.session() as session:
            if not session:
                raise RuntimeError("Database not connected")
            result = await session.execute(
                select(UserPreferences).where(UserPreferences.user_id == user_id)
            )
            prefs = result.scalar_one_or_none()
            
            if prefs:
                prefs.settings = settings or {}
                from datetime import datetime
                prefs.updated_at = datetime.utcnow()
            else:
                prefs = UserPreferences(user_id=user_id, settings=settings or {})
                session.add(prefs)
            
            await session.flush()
            await session.refresh(prefs)
            return prefs
    
    # Timer operations
    async def create_timer(
        self,
        action: str,
        scheduled_time,
        duration_seconds: int,
        user_id: str = "default",
        conversation_id: Optional[str] = None,
        command_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[ScheduledTimer]:
        """Create a new scheduled timer"""
        async with self.session() as session:
            if not session:
                return None
            timer = ScheduledTimer(
                action=action,
                scheduled_time=scheduled_time,
                duration_seconds=duration_seconds,
                user_id=user_id,
                conversation_id=conversation_id,
                command_data=command_data,
            )
            session.add(timer)
            await session.flush()
            await session.refresh(timer)
            return timer
    
    async def get_active_timers(self, user_id: str = "default") -> List[ScheduledTimer]:
        """Get all active timers for a user"""
        async with self.session() as session:
            if not session:
                return []
            result = await session.execute(
                select(ScheduledTimer)
                .where(ScheduledTimer.user_id == user_id)
                .where(ScheduledTimer.status == "active")
                .order_by(ScheduledTimer.scheduled_time.asc())
            )
            return result.scalars().all()
    
    async def get_timer_by_id(self, timer_id: str) -> Optional[ScheduledTimer]:
        """Get timer by ID"""
        async with self.session() as session:
            if not session:
                return None
            result = await session.execute(
                select(ScheduledTimer).where(ScheduledTimer.id == timer_id)
            )
            return result.scalar_one_or_none()
    
    async def cancel_timer(self, timer_id: str) -> bool:
        """Cancel a timer by ID"""
        async with self.session() as session:
            if not session:
                return False
            result = await session.execute(
                select(ScheduledTimer).where(ScheduledTimer.id == timer_id)
            )
            timer = result.scalar_one_or_none()
            if timer and timer.status == "active":
                timer.status = "cancelled"
                return True
            return False
    
    async def cancel_timers_by_action(self, action: str, user_id: str = "default") -> int:
        """Cancel all active timers for a specific action"""
        async with self.session() as session:
            if not session:
                return 0
            result = await session.execute(
                select(ScheduledTimer)
                .where(ScheduledTimer.user_id == user_id)
                .where(ScheduledTimer.action == action)
                .where(ScheduledTimer.status == "active")
            )
            timers = result.scalars().all()
            count = 0
            for timer in timers:
                timer.status = "cancelled"
                count += 1
            return count
    
    async def complete_timer(self, timer_id: str, error_message: Optional[str] = None) -> bool:
        """Mark timer as completed or failed"""
        async with self.session() as session:
            if not session:
                return False
            result = await session.execute(
                select(ScheduledTimer).where(ScheduledTimer.id == timer_id)
            )
            timer = result.scalar_one_or_none()
            if timer:
                timer.status = "failed" if error_message else "completed"
                timer.error_message = error_message
                return True
            return False


# Global client instance
_db_client: Optional[NeonDBClient] = None
_db_connect_lock = asyncio.Lock()


async def get_db_client() -> NeonDBClient:
    """Get the client, retrying a failed startup connection after cooldown."""
    global _db_client
    if _db_client is None or (
        _db_client.session_maker is None
        and time.monotonic() >= _db_client.next_reconnect_at
    ):
        async with _db_connect_lock:
            if _db_client is None:
                _db_client = NeonDBClient()
            if _db_client.session_maker is None and time.monotonic() >= _db_client.next_reconnect_at:
                await _db_client.connect()
                if _db_client.session_maker is not None:
                    await _db_client.create_tables()
    return _db_client


async def close_db_client():
    """Close global database client"""
    global _db_client
    if _db_client:
        await _db_client.disconnect()
        _db_client = None

