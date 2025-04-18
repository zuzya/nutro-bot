#!/usr/bin/env python3
import os
from dotenv import load_dotenv
from alembic.config import Config
from alembic import command

# Load environment variables
load_dotenv('.env')

# Get database configuration
db_user = os.getenv('DB_USER')
db_password = os.getenv('DB_PASSWORD')
db_name = os.getenv('DB_NAME')
db_host = os.getenv('DB_HOST')
db_port = os.getenv('DB_PORT')

# Create database URL
db_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
print(f"Connecting to database: {db_url}")

# Create Alembic configuration
alembic_cfg = Config("alembic.ini")
alembic_cfg.set_main_option("sqlalchemy.url", db_url)

# Run migrations
print("Running migrations...")
command.upgrade(alembic_cfg, "head")
print("Migrations completed successfully!") 