import os
import psycopg2
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

class Database:
    def __init__(self):
        self.conn = None
        self.connect()

    def connect(self):
        """Create a connection to the database."""
        print("Connecting to database with environment variables...")
        
        # Get database configuration from environment variables
        db_user = os.getenv('DB_USER')
        db_password = os.getenv('DB_PASSWORD')
        db_name = os.getenv('DB_NAME')
        db_host = os.getenv('DB_HOST')
        db_port = os.getenv('DB_PORT')

        # Validate environment variables
        if not all([db_user, db_password, db_name, db_host, db_port]):
            raise ValueError("Missing required database environment variables")

        if not self.conn:
            self.conn = psycopg2.connect(
                user=db_user,
                password=db_password,
                database=db_name,
                host=db_host,
                port=db_port
            )

    def init_db(self):
        """Initialize the database schema."""
        with self.conn.cursor() as cur:
            # Create users table
            cur.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create goals table
            cur.execute('''
                CREATE TABLE IF NOT EXISTS goals (
                    user_id BIGINT PRIMARY KEY REFERENCES users(user_id),
                    calories INTEGER,
                    protein INTEGER,
                    fat INTEGER,
                    carbs INTEGER,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create meals table
            cur.execute('''
                CREATE TABLE IF NOT EXISTS meals (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT REFERENCES users(user_id),
                    description TEXT,
                    calories INTEGER,
                    protein INTEGER,
                    fat INTEGER,
                    carbs INTEGER,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            ''')
        self.conn.commit()

    def ensure_user_exists(self, user_id: int):
        """Ensure user exists in the database."""
        with self.conn.cursor() as cur:
            cur.execute(
                'INSERT INTO users (user_id) VALUES (%s) ON CONFLICT DO NOTHING',
                (user_id,)
            )
        self.conn.commit()

    def save_meal(self, user_id: int, description: str, analysis: dict):
        """Save a meal to the database."""
        self.ensure_user_exists(user_id)
        
        with self.conn.cursor() as cur:
            cur.execute('''
                INSERT INTO meals (user_id, description, calories, protein, fat, carbs)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (user_id, description, analysis['calories'], analysis['protein'],
                analysis['fat'], analysis['carbs']))
        self.conn.commit()

    def get_today_meals(self, user_id: int):
        """Get all meals for today."""
        today = datetime.now(timezone.utc).date()
        
        with self.conn.cursor() as cur:
            cur.execute('''
                SELECT description, calories, protein, fat, carbs
                FROM meals
                WHERE user_id = %s
                AND DATE(created_at AT TIME ZONE 'UTC') = %s
                ORDER BY created_at DESC
            ''', (user_id, today))
            return cur.fetchall()

    def set_user_goals(self, user_id: int, goals: dict):
        """Set user's nutrition goals."""
        self.ensure_user_exists(user_id)
        
        with self.conn.cursor() as cur:
            cur.execute('''
                INSERT INTO goals (user_id, calories, protein, fat, carbs)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE
                SET calories = %s, protein = %s, fat = %s, carbs = %s,
                    updated_at = CURRENT_TIMESTAMP
            ''', (user_id, goals['calories'], goals['protein'],
                goals['fat'], goals['carbs'],
                goals['calories'], goals['protein'],
                goals['fat'], goals['carbs']))
        self.conn.commit()

    def get_user_progress(self, user_id: int):
        """Get user's progress for today."""
        today = datetime.now(timezone.utc).date()
        
        with self.conn.cursor() as cur:
            # Get today's meals
            cur.execute('''
                SELECT calories, protein, fat, carbs
                FROM meals
                WHERE user_id = %s
                AND DATE(created_at AT TIME ZONE 'UTC') = %s
            ''', (user_id, today))
            meals = cur.fetchall()
            
            # Get user's goals
            cur.execute('''
                SELECT calories, protein, fat, carbs
                FROM goals
                WHERE user_id = %s
            ''', (user_id,))
            goals = cur.fetchone()
            
            if not goals:
                return None
            
            # Calculate totals
            totals = {
                'calories': sum(meal[0] for meal in meals),
                'protein': sum(meal[1] for meal in meals),
                'fat': sum(meal[2] for meal in meals),
                'carbs': sum(meal[3] for meal in meals),
                'goal_calories': goals[0],
                'goal_protein': goals[1],
                'goal_fat': goals[2],
                'goal_carbs': goals[3]
            }
            
            return totals 