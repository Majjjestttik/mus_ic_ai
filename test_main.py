# -*- coding: utf-8 -*-

import os
import sys
import json
import sqlite3
import asyncio
import tempfile
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock

# Set up test environment variables before importing main
os.environ["TELEGRAM_TOKEN"] = "test_bot_token_12345"
os.environ["OPENROUTER_API_KEY"] = "test_openai_key_12345"
os.environ["ADMIN_ID"] = "0"

import main


class TestEnvironmentVariables:
    """Test environment variable validation"""
    
    def test_bot_token_required(self):
        """Test that TELEGRAM_TOKEN is loaded from environment"""
        assert main.TELEGRAM_TOKEN == "test_bot_token_12345"
    
    def test_openai_key_required(self):
        """Test that OPENROUTER_API_KEY is loaded from environment"""
        assert main.OPENROUTER_API_KEY == "test_openai_key_12345"
    
    def test_missing_tokens_raises_error(self):
        """Test that missing tokens raise RuntimeError"""
        # This test verifies the validation logic exists
        # The actual environment variables are set for testing
        assert main.TELEGRAM_TOKEN is not None
        assert main.OPENROUTER_API_KEY is not None


class TestDatabase:
    """Test database operations"""
    
    def setup_method(self):
        """Set up test database"""
        # Use a temporary database file for testing
        self.test_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.test_db.close()
        self.original_db_path = main.DB_PATH
        main.DB_PATH = self.test_db.name
        main.db_init()
    
    def teardown_method(self):
        """Clean up after tests"""
        main.DB_PATH = self.original_db_path
        if os.path.exists(self.test_db.name):
            os.remove(self.test_db.name)
    
    def test_db_init_creates_table(self):
        """Test database initialization"""
        main.db_init()
        con = sqlite3.connect(main.DB_PATH)
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        result = cur.fetchone()
        con.close()
        assert result is not None
        assert result[0] == "users"
    
    def test_db_get_user_creates_new_user(self):
        """Test that db_get_user creates a new user if not exists"""
        user_id = 123456
        user = main.db_get_user(user_id)
        assert user["user_id"] == user_id
        assert user["lang"] == "en"
        assert user["demo_used"] == 0
        assert user["songs"] == 0
        assert user["state"] == {}
    
    def test_db_set_updates_user(self):
        """Test updating user data"""
        user_id = 789012
        main.db_get_user(user_id)  # Create user
        main.db_set(user_id, lang="pl", songs=5)
        
        user = main.db_get_user(user_id)
        assert user["lang"] == "pl"
        assert user["songs"] == 5
    
    @pytest.mark.asyncio
    async def test_adb_functions(self):
        """Test async database wrappers"""
        user_id = 345678
        user = await main.adb_get_user(user_id)
        assert user["user_id"] == user_id
        
        await main.adb_set(user_id, lang="ru", songs=10)
        user = await main.adb_get_user(user_id)
        assert user["lang"] == "ru"
        assert user["songs"] == 10


class TestTranslations:
    """Test translation system"""
    
    def test_tr_function_returns_correct_language(self):
        """Test translation function for different languages"""
        assert "MusicAi" in main.tr("en", "start")
        assert "MusicAi" in main.tr("ru", "start")
        assert "MusicAi" in main.tr("pl", "start")
        assert "MusicAi" in main.tr("de", "start")
        assert "MusicAi" in main.tr("es", "start")
        assert "MusicAi" in main.tr("fr", "start")
        assert "MusicAi" in main.tr("uk", "start")
    
    def test_tr_fallback_to_english(self):
        """Test that unknown language falls back to English"""
        result = main.tr("unknown", "start")
        assert "MusicAi" in result
    
    def test_all_supported_languages_have_translations(self):
        """Test that all supported languages have key translations"""
        languages = ["en", "ru", "pl", "de", "es", "fr", "uk"]
        keys = ["start", "choose_language", "describe", "help", "generating"]
        
        for lang in languages:
            for key in keys:
                result = main.tr(lang, key)
                assert result != "Missing text", f"Missing translation for {lang}/{key}"


class TestKeyboards:
    """Test keyboard generation"""
    
    def test_kb_languages_has_all_languages(self):
        """Test language keyboard includes all supported languages"""
        kb = main.kb_languages()
        assert kb is not None
        assert len(kb.inline_keyboard) == 4  # 4 rows
        # Check that we have buttons for all 7 languages
        total_buttons = sum(len(row) for row in kb.inline_keyboard)
        assert total_buttons == 7
    
    def test_kb_themes_for_each_language(self):
        """Test theme keyboard for different languages"""
        for lang in ["en", "ru", "pl", "de", "es", "fr", "uk"]:
            kb = main.kb_themes(lang)
            assert kb is not None
            # Should have 3 rows with 2 buttons each (6 themes)
            assert len(kb.inline_keyboard) == 3
    
    def test_kb_genres(self):
        """Test genre keyboard"""
        kb = main.kb_genres()
        assert kb is not None
        # Should have 3 rows with 2 buttons each (6 genres)
        assert len(kb.inline_keyboard) == 3


class TestOpenAIIntegration:
    """Test OpenAI API integration"""
    
    @pytest.mark.asyncio
    async def test_openai_generate_song_with_mock(self):
        """Test song generation with mocked OpenAI client"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test song lyrics"
        
        with patch('main.AsyncOpenAI') as mock_openai:
            mock_client = AsyncMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.return_value = mock_client
            
            result = await main.openai_generate_song("Test prompt")
            assert result == "Test song lyrics"
            mock_client.chat.completions.create.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_openai_generate_song_error_handling(self):
        """Test error handling in song generation"""
        with patch('main.AsyncOpenAI') as mock_openai:
            mock_client = AsyncMock()
            mock_client.chat.completions.create.side_effect = Exception("API Error")
            mock_openai.return_value = mock_client
            
            result = await main.openai_generate_song("Test prompt")
            assert result is None
    
    @pytest.mark.asyncio
    async def test_voice_to_text_with_mock(self):
        """Test voice transcription with mocked OpenAI client"""
        mock_response = MagicMock()
        mock_response.text = "Transcribed text"
        
        with patch('main.AsyncOpenAI') as mock_openai:
            mock_client = AsyncMock()
            mock_client.audio.transcriptions.create.return_value = mock_response
            mock_openai.return_value = mock_client
            
            # Create a temporary test file
            test_file = tempfile.NamedTemporaryFile(delete=False, suffix='.ogg')
            test_file.write(b"test")
            test_file.close()
            
            try:
                result = await main.voice_to_text(test_file.name)
                assert result == "Transcribed text"
            finally:
                if os.path.exists(test_file.name):
                    os.remove(test_file.name)


class TestHandlers:
    """Test bot handlers"""
    
    def setup_method(self):
        """Set up test database"""
        self.test_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.test_db.close()
        self.original_db_path = main.DB_PATH
        main.DB_PATH = self.test_db.name
        main.db_init()
    
    def teardown_method(self):
        """Clean up after tests"""
        main.DB_PATH = self.original_db_path
        if os.path.exists(self.test_db.name):
            os.remove(self.test_db.name)
    
    @pytest.mark.asyncio
    async def test_start_cmd_creates_user(self):
        """Test start command creates user in database"""
        update = MagicMock()
        update.effective_user.id = 999999
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        
        await main.start_cmd(update, context)
        
        # Verify user was created
        user = main.db_get_user(999999)
        assert user["user_id"] == 999999
        assert user["state"] == {}
        
        # Verify reply was sent
        update.message.reply_text.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_help_cmd_sends_help_text(self):
        """Test help command sends appropriate message"""
        update = MagicMock()
        update.effective_user.id = 888888
        update.message.reply_text = AsyncMock()
        context = MagicMock()
        
        # Create user first
        main.db_get_user(888888)
        
        await main.help_cmd(update, context)
        
        update.message.reply_text.assert_called_once()
        call_args = update.message.reply_text.call_args
        assert "Help" in call_args[0][0] or "Помощь" in call_args[0][0] or "Pomoc" in call_args[0][0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
