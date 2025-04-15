# Food Tracking Telegram Bot

A Telegram bot that helps users track their food intake, analyze nutritional value, and receive personalized recommendations.

## Features

- Track daily food intake
- Analyze nutritional value using OpenAI
- Set and track nutrition goals
- View daily progress
- Get personalized recommendations
- Support for different diet types (weight loss, muscle gain, maintenance, keto)

## Setup with Docker Compose

1. Clone the repository:
```bash
git clone <repository-url>
cd food-tracker-bot
```

2. Set up environment variables:
```bash
cp .env.example .env
```
Edit `.env` file with your credentials:
- Telegram Bot Token (get from @BotFather)
- OpenAI API Key
- Database credentials (default values are provided)

3. Start PostgreSQL with Docker Compose:
```bash
docker-compose up -d postgres
```

4. Wait for PostgreSQL to be ready (check with `docker-compose ps`)

5. Initialize the database schema:
```bash
python -c "from database import Database; Database().init_db()"
```

6. Start the bot:
```bash
python bot.py
```

## Setup without Docker

1. Clone the repository:
```bash
git clone <repository-url>
cd food-tracker-bot
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
cp .env.example .env
```
Edit `.env` file with your credentials:
- Telegram Bot Token (get from @BotFather)
- OpenAI API Key
- Database credentials

4. Set up PostgreSQL database:
```bash
createdb food_tracker
```

5. Initialize the database schema:
```bash
python -c "from database import Database; Database().init_db()"
```

## Running the Bot

### With Docker Compose (PostgreSQL only)
```bash
# Start PostgreSQL
docker-compose up -d postgres

# Start the bot
python bot.py
```

### Without Docker
```bash
python bot.py
```

## Usage

1. Start the bot in Telegram by sending `/start`
2. Set your nutrition goals using `/set_goals`
3. Add meals using `/add_meal` followed by a description
4. View today's meals using `/today`
5. Check your progress using `/progress`

## Commands

- `/start` - Start the bot
- `/help` - Show help message
- `/set_goals` - Set nutrition goals
- `/add_meal` - Add a meal
- `/today` - View today's meals
- `/progress` - View progress

## Contributing

Feel free to submit issues and enhancement requests. 