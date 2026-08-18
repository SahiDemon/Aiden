from unittest.mock import MagicMock
from src.core.assistant import AidenAssistant


def test_is_unhelpful_question_response_detects_meta_refusals():
    # Structural refusals / placeholders with no commands
    assert AidenAssistant._is_unhelpful_question_response({"response": "I can look that up for you. Please give me a moment.", "commands": []}) is True
    assert AidenAssistant._is_unhelpful_question_response({"response": "I can't provide summaries of TV show episodes. Is there anything else?", "commands": []}) is True
    assert AidenAssistant._is_unhelpful_question_response({"response": "As an AI language model, I do not have access to that.", "commands": []}) is True
    assert AidenAssistant._is_unhelpful_question_response({"response": "Let me check that for you.", "commands": []}) is True


def test_is_unhelpful_question_response_ignores_valid_answers_and_commands():
    # Valid text answer
    assert AidenAssistant._is_unhelpful_question_response({"response": "Fred Johnson is a former Martian marine and OPA leader.", "commands": []}) is False
    
    # Response with commands present (even if response text is short)
    assert AidenAssistant._is_unhelpful_question_response({"response": "Searching...", "commands": [{"type": "shell_command"}]}) is False


def test_build_search_fallback_response_generates_google_search():
    assistant = MagicMock()
    fallback = AidenAssistant._build_search_fallback_response(assistant, "The Expanse season 1 episode 5 summary")
    
    assert fallback["intent"] == "question"
    assert len(fallback["commands"]) == 1
    assert fallback["commands"][0]["type"] == "shell_command"
    assert "https://www.google.com/search?q=The+Expanse+season+1+episode+5+summary" in fallback["commands"][0]["params"]["command"]
    assert "Searching Google for" in fallback["response"]
