"""AI module - Groq client for context-aware LLM processing"""
from src.ai.groq_client import GroqClient, get_groq_client, close_groq_client

__all__ = ["GroqClient", "get_groq_client", "close_groq_client"]
