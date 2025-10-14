"""
Configuration Management with Pydantic
Handles all application settings with type validation and environment variable support
"""
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class GroqConfig(BaseSettings):
    """Groq AI API Configuration - Entirely FREE and super fast!"""
    model_config = SettingsConfigDict(
        env_prefix="GROQ_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    api_key: str = Field(..., description="Groq Cloud API Key")
    base_url: str = Field(default="https://api.groq.com/openai/v1/chat/completions", description="Groq API endpoint")
    model: str = Field(default="llama-3.1-8b-instant", description="Groq model to use")
    max_tokens: int = Field(default=500, description="Maximum tokens in response")
    temperature: float = Field(default=0.3, description="Response creativity (0-1)")


class DatabaseConfig(BaseSettings):
    """Neon DB Configuration"""
    model_config = SettingsConfigDict(
        env_prefix="NEON_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    database_url: str = Field(..., description="PostgreSQL connection URL")
    pool_size: int = Field(default=5, description="Connection pool size")
    max_overflow: int = Field(default=10, description="Max connections beyond pool_size")
    pool_timeout: int = Field(default=30, description="Pool connection timeout")


class RedisConfig(BaseSettings):
    """Redis Cloud Configuration"""
    model_config = SettingsConfigDict(
        env_prefix="REDIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    url: str = Field(..., description="Redis connection URL")
    decode_responses: bool = Field(default=True, description="Decode Redis responses to strings")
    socket_timeout: int = Field(default=5, description="Socket timeout in seconds")
    socket_connect_timeout: int = Field(default=5, description="Connection timeout")


class AppConfig(BaseSettings):
    """Application Settings"""
    name: str = Field(default="Aiden", description="Application name")
    user_name: str = Field(default="Boss", description="User's preferred name")
    wake_word: str = Field(default="aiden", description="Wake word for voice activation")
    hotkey: str = Field(default="ctrl+shift+space", description="Hotkey combination for voice activation")
    debug: bool = Field(default=False, description="Enable debug mode")


class APIConfig(BaseSettings):
    """FastAPI Server Configuration"""
    host: str = Field(default="localhost", description="API server host")
    port: int = Field(default=5000, description="API server port")
    reload: bool = Field(default=False, description="Enable auto-reload")


class ESP32Config(BaseSettings):
    """ESP32 Smart Home Configuration"""
    model_config = SettingsConfigDict(
        env_prefix="ESP32_",
        extra="ignore"
    )
    
    enabled: bool = Field(default=True, description="Enable ESP32 integration")
    ip_address: str = Field(default="192.168.1.180", description="ESP32 IP address")
    timeout: int = Field(default=5, description="Request timeout")
    retry_attempts: int = Field(default=3, description="Number of retry attempts")


class SpeechConfig(BaseSettings):
    """Speech Recognition & Synthesis Configuration"""
    tts_voice: str = Field(default="en-US-AvaNeural", description="Edge TTS voice")
    tts_rate: float = Field(default=1.2, description="TTS speech rate")
    stt_language: str = Field(default="en-US", description="STT language")
    stt_timeout: int = Field(default=10, description="STT timeout in seconds")
    stt_energy_threshold: int = Field(default=600, description="Audio energy threshold")
    stt_pause_threshold: float = Field(default=0.8, description="Pause detection threshold")
    vosk_model_path: str = Field(default="vosk_models/vosk-model-small-en-us-0.15", description="Vosk model path")


class CacheConfig(BaseSettings):
    """Caching Configuration"""
    enable_caching: bool = Field(default=True, description="Enable caching")
    ttl_context: int = Field(default=300, description="Context cache TTL (seconds)")
    ttl_app_paths: int = Field(default=86400, description="App paths cache TTL")
    ttl_llm_response: int = Field(default=3600, description="LLM response cache TTL")
    ttl_tts_audio: int = Field(default=3600, description="TTS audio cache TTL")


class Settings(BaseSettings):
    """Main Application Settings"""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # Sub-configurations - all loaded from .env file
    groq: GroqConfig = Field(default_factory=GroqConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    app: AppConfig = Field(default_factory=AppConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    esp32: ESP32Config = Field(default_factory=ESP32Config)
    speech: SpeechConfig = Field(default_factory=SpeechConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    
    def model_post_init(self, __context) -> None:
        """Validate that required env vars are set"""
        # Check critical settings
        if not self.groq.api_key:
            raise ValueError("❌ GROQ_API_KEY must be set in .env file")
        if not self.database.database_url:
            raise ValueError("❌ NEON_DATABASE_URL must be set in .env file")  
        if not self.redis.url:
            raise ValueError("❌ REDIS_URL must be set in .env file")
        
        # Log loaded configuration (hide sensitive data)
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"✅ Config loaded: Groq model={self.groq.model}, API={self.api.host}:{self.api.port}")


# Global settings instance
settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or create global settings instance"""
    global settings
    if settings is None:
        settings = Settings()
    return settings


def reload_settings() -> Settings:
    """Reload settings from environment/file"""
    global settings
    settings = Settings()
    return settings

