# mus_ic_ai

MusicAi PRO - A Telegram bot for generating song lyrics and music using AI.

## Features

- **Song Lyrics Generation**: Generate creative song lyrics using OpenRouter LLM API
- **Music Generation**: Generate actual songs with vocals and instrumentals using Suno AI API
- **Multi-language Support**: Supports Russian, English, Polish, German, Spanish, Italian, and French
- **Customizable Settings**: Choose genre, mood, vocal type, energy level, and song structure
- **Credit System**: Purchase credits using Telegram Stars (XTR)
- **History Tracking**: Keep track of your generated songs

## Environment Variables

The following environment variables are required:

- `TELEGRAM_TOKEN`: Your Telegram bot token
- `OPENROUTER_API_KEY`: API key for OpenRouter (lyrics generation)
- `SUNO_API_KEY`: API key for Suno AI (music generation) - optional
- `SUNO_API_URL`: Suno API endpoint URL (default: `https://api.sunoapi.org`)
- `SUNO_MODEL`: Suno AI model version (default: `chirp-v3-5`)
- `ADMIN_ID`: Telegram user ID for admin (optional)

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up environment variables (create a `.env` file or use your hosting platform's environment variables):
```
TELEGRAM_TOKEN=your_telegram_bot_token
OPENROUTER_API_KEY=your_openrouter_key
SUNO_API_KEY=your_suno_api_key
```

3. Run the bot:
```bash
python main.py
```

## Usage

1. Start a conversation with the bot using `/start`
2. Send a song topic or theme as a text message
3. The bot will generate song lyrics with a style prompt
4. If Suno API is configured, click the "🎵 Generate Music" button to create actual songs with vocals and instrumentals
5. The bot will return 2 song variations

## Testing

Run the test suite:
```bash
pytest test_suno_integration.py -v
```

## Architecture

- **OpenRouter API**: Generates song lyrics and style prompts
- **Suno API**: Converts lyrics into complete songs with music and vocals
- **SQLite Database**: Stores user preferences and credit balances
- **Telegram Bot API**: Handles user interactions and payments