import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
from src.utils.media_idle_monitor import MediaIdleMonitor


@pytest.fixture
def mock_monitor():
    monitor = MediaIdleMonitor()
    return monitor


def test_monitor_init(mock_monitor):
    assert mock_monitor.polling_interval == 30.0
    assert mock_monitor.running is False


@pytest.mark.asyncio
@patch("src.utils.media_idle_monitor.get_settings")
@patch("src.utils.media_idle_monitor.MediaIdleMonitor.is_media_playing")
@patch("src.utils.media_idle_monitor.MediaIdleMonitor.get_idle_time_seconds")
@patch("src.utils.media_idle_monitor.MediaIdleMonitor._trigger_shutdown_sequence")
async def test_idle_condition_when_paused_and_idle(mock_trigger, mock_idle_sec, mock_playing, mock_settings, mock_monitor):
    mock_settings.return_value.app.media_idle_shutdown_enabled = True
    mock_settings.return_value.app.media_idle_timeout_minutes = 15
    mock_playing.return_value = False
    mock_idle_sec.return_value = 1000.0
    
    await mock_monitor._check_idle_state()
    
    assert mock_monitor._warning_triggered is True
    mock_trigger.assert_called_once_with(15)


@pytest.mark.asyncio
@patch("src.utils.media_idle_monitor.get_settings")
@patch("src.utils.media_idle_monitor.MediaIdleMonitor.is_media_playing")
@patch("src.utils.media_idle_monitor.MediaIdleMonitor.get_idle_time_seconds")
@patch("src.utils.media_idle_monitor.MediaIdleMonitor._trigger_shutdown_sequence")
async def test_idle_condition_when_playing(mock_trigger, mock_idle_sec, mock_playing, mock_settings, mock_monitor):
    mock_settings.return_value.app.media_idle_shutdown_enabled = True
    mock_settings.return_value.app.media_idle_timeout_minutes = 15
    mock_playing.return_value = True
    mock_idle_sec.return_value = 1000.0
    
    await mock_monitor._check_idle_state()
    
    assert mock_monitor._warning_triggered is False
    mock_trigger.assert_not_called()
