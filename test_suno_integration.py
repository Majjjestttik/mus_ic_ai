# -*- coding: utf-8 -*-
"""
Test Suno API integration
"""

import os
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import aiohttp

# Set up test environment variables before importing main
os.environ["TELEGRAM_TOKEN"] = "test_token_12345"
os.environ["OPENROUTER_API_KEY"] = "test_openai_key"
os.environ["SUNO_API_KEY"] = "test_suno_key"
os.environ["ADMIN_ID"] = "0"

import main


class TestSunoAPIClient:
    """Test Suno API client functions"""
    
    @pytest.mark.asyncio
    async def test_suno_generate_song_success(self):
        """Test successful song generation request"""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "data": {"taskId": "test-task-123"}
        })
        
        mock_session = MagicMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        
        with patch('aiohttp.ClientSession.post', return_value=mock_response):
            async with aiohttp.ClientSession() as session:
                result = await main.suno_generate_song(
                    session,
                    lyrics="Test lyrics",
                    style="Pop Rock",
                    title="Test Song"
                )
        
        assert result.ok is True
        assert result.task_id == "test-task-123"
    
    @pytest.mark.asyncio
    async def test_suno_generate_song_no_key(self):
        """Test generation fails when API key is missing"""
        original_key = main.SUNO_API_KEY
        main.SUNO_API_KEY = ""
        
        try:
            async with aiohttp.ClientSession() as session:
                result = await main.suno_generate_song(
                    session,
                    lyrics="Test lyrics",
                    style="Pop Rock"
                )
            
            assert result.ok is False
            assert result.error == "NO_SUNO_KEY"
        finally:
            main.SUNO_API_KEY = original_key
    
    @pytest.mark.asyncio
    async def test_suno_poll_task_completed(self):
        """Test polling for completed task"""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "status": "complete",
            "output": [
                {"audio_url": "https://example.com/song1.mp3"},
                {"audio_url": "https://example.com/song2.mp3"}
            ]
        })
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        
        with patch('aiohttp.ClientSession.get', return_value=mock_response):
            async with aiohttp.ClientSession() as session:
                result = await main.suno_poll_task(
                    session,
                    task_id="test-task-123",
                    max_attempts=1
                )
        
        assert result.ok is True
        assert len(result.audio_urls) == 2
        assert "song1.mp3" in result.audio_urls[0]
    
    @pytest.mark.asyncio
    async def test_suno_poll_task_failed(self):
        """Test polling for failed task"""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "status": "failed",
            "error": "Generation failed"
        })
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        
        with patch('aiohttp.ClientSession.get', return_value=mock_response):
            async with aiohttp.ClientSession() as session:
                result = await main.suno_poll_task(
                    session,
                    task_id="test-task-123",
                    max_attempts=1
                )
        
        assert result.ok is False
        assert "FAILED" in result.error


class TestSunoDataclasses:
    """Test Suno dataclasses"""
    
    def test_suno_result_initialization(self):
        """Test SunoResult initialization"""
        result = main.SunoResult(ok=True, task_id="123")
        assert result.ok is True
        assert result.task_id == "123"
        assert result.audio_urls == []
        assert result.error == ""
    
    def test_suno_result_with_audio_urls(self):
        """Test SunoResult with audio URLs"""
        result = main.SunoResult(
            ok=True,
            task_id="123",
            audio_urls=["url1", "url2"]
        )
        assert len(result.audio_urls) == 2


class TestTranslations:
    """Test new translations for Suno features"""
    
    def test_suno_translations_exist(self):
        """Test that Suno-related translations exist"""
        test_user = {"lang": "en"}
        
        # Test English translations
        assert main.tr(test_user, "generate_music") != ""
        assert main.tr(test_user, "generating_music") != ""
        assert main.tr(test_user, "music_ready") != ""
        assert main.tr(test_user, "no_suno_key") != ""
        assert main.tr(test_user, "suno_error") != ""
        assert main.tr(test_user, "suno_timeout") != ""
        
        # Test Russian translations
        test_user_ru = {"lang": "ru"}
        assert main.tr(test_user_ru, "generate_music") != ""
        assert "Генерир" in main.tr(test_user_ru, "generate_music") or "музык" in main.tr(test_user_ru, "generate_music")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
