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

- `BOT_TOKEN`: Your Telegram bot token
- `OPENROUTER_API_KEY`: API key for OpenRouter (lyrics generation)
- `PIAPI_API_KEY`: API key for PIAPI (music generation via Suno)
- `PIAPI_BASE_URL`: PIAPI base URL (e.g., `https://your-piapi-server.com`)
- `PIAPI_GENERATE_PATH`: Path to Suno music generation endpoint (default: `/suno/music`)
- `DATABASE_URL`: PostgreSQL database connection string
- `STRIPE_SECRET_KEY`: Stripe API secret key (for payments)
- `STRIPE_WEBHOOK_SECRET`: Stripe webhook secret
- `BOT_USERNAME`: Your bot username (for redirect URLs)
- `ADMIN_ID`: Telegram user ID for admin (optional)

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up environment variables (create a `.env` file or use your hosting platform's environment variables):
```
BOT_TOKEN=your_telegram_bot_token
OPENROUTER_API_KEY=your_openrouter_key
PIAPI_API_KEY=your_piapi_key
PIAPI_BASE_URL=https://your-piapi-server.com
DATABASE_URL=postgresql://user:pass@host/db
STRIPE_SECRET_KEY=your_stripe_key
STRIPE_WEBHOOK_SECRET=your_webhook_secret
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