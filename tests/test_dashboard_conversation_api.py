from types import SimpleNamespace
from unittest.mock import AsyncMock
import httpx
import pytest
import src.api.server as server

@pytest.mark.asyncio
async def test_new_dashboard_conversation_resets_context_without_microphone(monkeypatch):
    import src.core.assistant as assistant_module
    manager = SimpleNamespace(end_conversation=AsyncMock(), start_conversation=AsyncMock(return_value='fresh-id'))
    monkeypatch.setattr(assistant_module, 'get_assistant', AsyncMock(return_value=SimpleNamespace(context_manager=manager)))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url='http://test') as client:
        response = await client.post('/api/v1/conversation/new')
    assert response.status_code == 200
    assert response.json()['conversation_id'] == 'fresh-id'
    manager.end_conversation.assert_awaited_once()
    manager.start_conversation.assert_awaited_once_with(mode='text')

@pytest.mark.asyncio
async def test_history_returns_saved_messages_for_dashboard(monkeypatch):
    conversation = SimpleNamespace(to_dict=lambda: {'id': 'saved-id'})
    message = SimpleNamespace(to_dict=lambda: {'role': 'assistant', 'content': 'Saved answer'})
    database = SimpleNamespace(get_conversation=AsyncMock(return_value=conversation), get_conversation_messages=AsyncMock(return_value=[message]))
    monkeypatch.setattr(server, 'get_db_client', AsyncMock(return_value=database))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url='http://test') as client:
        response = await client.get('/api/v1/conversations/saved-id')
    assert response.status_code == 200
    assert response.json()['messages'] == [{'role': 'assistant', 'content': 'Saved answer'}]

@pytest.mark.asyncio
async def test_resume_restores_saved_context_before_followup(monkeypatch):
    import src.core.assistant as assistant_module
    message = SimpleNamespace(role='user', content='Remember the blue lamp', to_dict=lambda: {'role': 'user', 'content': 'Remember the blue lamp'})
    database = SimpleNamespace(get_conversation=AsyncMock(return_value=object()), get_conversation_messages=AsyncMock(return_value=[message]))
    manager = SimpleNamespace(get_context=AsyncMock(return_value={'history': []}), current_conversation_id=None)
    redis = SimpleNamespace(save_context=AsyncMock())
    monkeypatch.setattr(server, 'get_db_client', AsyncMock(return_value=database))
    monkeypatch.setattr(server, 'get_redis_client', AsyncMock(return_value=redis))
    monkeypatch.setattr(assistant_module, 'get_assistant', AsyncMock(return_value=SimpleNamespace(context_manager=manager)))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url='http://test') as client:
        response = await client.post('/api/v1/conversations/saved-id/resume')
    assert response.status_code == 200
    assert manager.current_conversation_id == 'saved-id'
    saved = redis.save_context.await_args.args[1]
    assert saved['history'] == [{'role': 'user', 'content': 'Remember the blue lamp'}]

@pytest.mark.asyncio
async def test_typed_message_creates_context_and_broadcasts_user(monkeypatch):
    from src.core.assistant import AidenAssistant
    import src.utils.websocket_broadcast as broadcasts
    manager = SimpleNamespace(current_conversation_id=None, start_conversation=AsyncMock())
    assistant = AidenAssistant.__new__(AidenAssistant)
    assistant.context_manager = manager
    assistant._process_user_message = AsyncMock(return_value='Ready')
    broadcast = AsyncMock()
    monkeypatch.setattr(broadcasts, 'broadcast_message', broadcast)
    monkeypatch.setattr(broadcasts, 'broadcast_voice_status', AsyncMock())
    assert await assistant.handle_text_message('Hello from my phone', source='web') == 'Ready'
    manager.start_conversation.assert_awaited_once_with(mode='text')
    assert broadcast.await_args.args[1]['role'] == 'user'
    assert broadcast.await_args.args[1]['content'] == 'Hello from my phone'
    assistant._process_user_message.assert_awaited_once_with('Hello from my phone', source='web')

@pytest.mark.asyncio
@pytest.mark.parametrize('input_type,expected_source', [('text', 'web_text'), ('voice', 'web')])
async def test_dashboard_request_routes_text_silently_and_preserves_voice(monkeypatch, input_type, expected_source):
    import src.core.assistant as assistant_module
    assistant = SimpleNamespace(handle_text_message=AsyncMock(return_value='Reply'))
    monkeypatch.setattr(assistant_module, 'get_assistant', AsyncMock(return_value=assistant))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url='http://test') as client:
        response = await client.post('/api/v1/conversation/message', json={'message':'Hello', 'source':'web', 'input_type':input_type, 'client_message_id':'request-1'})
    assert response.status_code == 200
    assistant.handle_text_message.assert_awaited_once_with('Hello', source=expected_source, client_message_id='request-1')

@pytest.mark.asyncio
async def test_silent_text_does_not_broadcast_voice_activity(monkeypatch):
    from src.core.assistant import AidenAssistant
    import src.utils.websocket_broadcast as broadcasts
    assistant = AidenAssistant.__new__(AidenAssistant)
    assistant.context_manager = SimpleNamespace(current_conversation_id='active')
    assistant._process_user_message = AsyncMock(return_value='Text reply')
    voice = AsyncMock()
    message = AsyncMock()
    monkeypatch.setattr(broadcasts, 'broadcast_voice_status', voice)
    monkeypatch.setattr(broadcasts, 'broadcast_message', message)
    assert await assistant.handle_text_message('Hello', source='web_text', client_message_id='request-1') == 'Text reply'
    voice.assert_not_awaited()
    assert message.await_args.args[1]['source'] == 'web_text'
    assert message.await_args.args[1]['client_message_id'] == 'request-1'

@pytest.mark.asyncio
async def test_silent_text_does_not_generate_or_queue_audio():
    from src.speech.tts import TTSEngine
    engine = TTSEngine.__new__(TTSEngine)
    engine._get_cached_audio = AsyncMock()
    await engine.speak('Silent reply', source='web_text')
    engine._get_cached_audio.assert_not_awaited()

