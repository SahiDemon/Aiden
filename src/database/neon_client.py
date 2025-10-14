"""
Neon DB Client
Async PostgreSQL database client using SQLAlchemy
"""
import logging
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.future import select
from sqlalchemy import text

from src.database.models import Base, Conversation, Message, CommandHistory, UserPreferences
from src.utils.config import get_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class NeonDBClient:
    """Async Neon DB client for PostgreSQL operations"""
    
    def __init__(self):
        self.settings = get_settings()
        self.engine = None
        self.session_maker = None
        
    async def connect(self):
        """Initialize database connection"""
        try:
            # Convert postgresql:// to postgresql+psycopg://
            db_url = self.settings.database.database_url
            if db_url.startswith("postgresql://"):
                db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
            
            # Psycopg 3 connection arguments
            # Psycopg handles SSL automatically based on connection string (sslmode parameter)
            connect_args = {
                "prepare_threshold": None,  # Disable prepared statements for better compatibility
                "connect_timeout": 10  # 10 second connection timeout
            }
            
            logger.info("Creating Neon DB engine...")
            # Create async engine with psycopg
            self.engine = create_async_engine(
                db_url,
                pool_size=self.settings.database.pool_size,
                max_overflow=self.settings.database.max_overflow,
                pool_timeout=self.settings.database.pool_timeout,
                echo=self.settings.app.debug,
                connect_args=connect_args,
                pool_pre_ping=True  # Verify connections before using
            )
            
            # Create session maker
            self.session_maker = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            logger.info("Testing Neon DB connection...")
            # Test connection with timeout
            import asyncio
            async with asyncio.timeout(15):  # 15 second total timeout
                async with self.engine.begin() as conn:
                    await conn.execute(text("SELECT 1"))
            
            logger.info("Connected to Neon DB successfully!")
            
        except asyncio.TimeoutError:
            logger.error("Neon DB connection timed out")
            logger.warning("Database features will be unavailable, but Aiden will continue running")
            self.engine = None
            self.session_maker = None
        except Exception as e:
            logger.error(f"Failed to connect to Neon DB: {e}")
            logger.warning("Database features will be unavailable, but Aiden will continue running")
            # Don't raise - allow app to continue without database
            self.engine = None
            self.session_maker = None
    
    async def disconnect(self):
        """Close database connection"""
        if self.engine:
            await self.engine.dispose()
            logger.info("Disconnected from Neon DB")
    
    async def create_tables(self):
        """Create all tables if they don't exist"""
        if not self.engine:
            logger.warning("Database not connected - skipping table creation")
            return
            
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
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
    async def create_conversation(self, user_id: str = "default", mode: str = "voice") -> Optional[Conversation]:
        """Create new conversation"""
        async with self.session() as session:
            if not session:
                return None
            conversation = Conversation(user_id=user_id, mode=mode)
            session.add(conversation)
            await session.flush()
            await session.refresh(conversation)
            return conversation
    
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
            await session.refresh(command)
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


# Global client instance
_db_client: Optional[NeonDBClient] = None


async def get_db_client() -> NeonDBClient:
    """Get or create global database client"""
    global _db_client
    if _db_client is None:
        _db_client = NeonDBClient()
        await _db_client.connect()
        await _db_client.create_tables()
    return _db_client


async def close_db_client():
    """Close global database client"""
    global _db_client
    if _db_client:
        await _db_client.disconnect()
        _db_client = None

