#!/bin/bash
set -e

# Run database migrations
echo "Running database migrations..."
if ! /opt/venv/bin/alembic upgrade head; then
    echo "Migration failed!"
    exit 1
fi

# Start the bot
echo "Starting the bot..."
python3 bot.py 