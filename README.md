# mus_ic_ai

A Telegram bot that helps users create songs based on descriptions in multiple languages using OpenAI's GPT-4.

## Features

- **Multi-language Support**: Polish, Ukrainian, English, German, French, Russian, Spanish
- **Intelligent Song Generation**: Uses OpenAI GPT-4 to create song lyrics based on user descriptions
- **Voice Message Support**: Transcribe voice messages to text using OpenAI Whisper
- **Multiple Themes**: Love, Funny, Holiday, Sad, Wedding, or custom themes
- **Multiple Genres**: Pop, Rap, Rock, Club, Classical, Disco Polo
- **SQLite Database**: Store user preferences and statistics
- **Demo Mode**: Free demo song for new users
- **Payment Integration**: Telegram Stars payment system for song credits

## Requirements

- Python 3.9+
- Telegram Bot Token
- OpenAI API Key

## Installation

1. Clone the repository:
```bash
git clone https://github.com/Majjjestttik/mus_ic_ai.git
cd mus_ic_ai
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
export TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
export OPENAI_API_KEY="your_openai_api_key"
export OWNER_TG_ID="your_telegram_user_id"  # Optional
```

4. Run the bot:
```bash
python main.py
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | Token from @BotFather on Telegram |
| `OPENAI_API_KEY` | Yes | OpenAI API key for GPT-4 and Whisper |
| `OWNER_TG_ID` | No | Owner's Telegram user ID (default: 1225282893) |

## Usage

1. Start the bot with `/start`
2. Select your preferred language
3. Choose a theme (or create a custom one)
4. Select a music genre
5. Describe your song or send a voice message
6. Receive your personalized song lyrics!

## Commands

- `/start` - Start the bot and select language
- `/help` - Display help information

## Testing

Run the test suite:
```bash
pytest test_main.py -v
```

## Database Schema

The bot uses SQLite with the following schema:

```sql
CREATE TABLE users (
    user_id INTEGER PRIMARY KEY,
    lang TEXT DEFAULT 'en',
    demo_used INTEGER DEFAULT 0,
    songs INTEGER DEFAULT 0,
    state_json TEXT DEFAULT '{}',
    updated_at INTEGER DEFAULT 0
)
```

## Architecture

- **main.py**: Main bot logic with handlers and API integration
- **test_main.py**: Comprehensive test suite
- **requirements.txt**: Python dependencies
- **musicai.db**: SQLite database (created automatically)

## Security

- Environment variables for sensitive data
- No hardcoded credentials
- Input validation and error handling
- Secure database operations
- Regular dependency updates

## License

This project is open source and available for educational purposes.
