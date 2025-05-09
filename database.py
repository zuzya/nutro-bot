import os
import logging
import time
from sqlalchemy import create_engine, func, and_, desc, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError
from datetime import datetime, timedelta
from models import Base, User, UserGoals, Meal
from dotenv import load_dotenv
import re

load_dotenv()

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, max_retries=5, retry_delay=5):
        """Initialize database connection with retry logic."""
        self.db_user = os.getenv('DB_USER')
        self.db_password = os.getenv('DB_PASSWORD')
        self.db_name = os.getenv('DB_NAME')
        self.db_host = os.getenv('DB_HOST')
        self.db_port = os.getenv('DB_PORT')
        
        # Create database URL with SSL settings
        self.db_url = f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}?sslmode=require"
        
        # Initialize connection with retries
        self.engine = None
        self.Session = None
        self._initialize_connection(max_retries, retry_delay)
        
        # Create tables
        Base.metadata.create_all(self.engine)
        logger.info("Database initialized and tables created")

    def _initialize_connection(self, max_retries, retry_delay):
        """Initialize database connection with retry logic."""
        for attempt in range(max_retries):
            try:
                logger.info(f"Attempting to connect to database (attempt {attempt + 1}/{max_retries})")
                self.engine = create_engine(
                    self.db_url,
                    pool_pre_ping=True,  # Enable connection health checks
                    pool_recycle=3600,   # Recycle connections after 1 hour
                    pool_size=5,         # Maximum number of connections
                    max_overflow=10      # Maximum number of connections that can be created above pool_size
                )
                self.Session = sessionmaker(bind=self.engine)
                
                # Test the connection
                with self.Session() as session:
                    session.execute(text("SELECT 1"))
                logger.info("Successfully connected to database")
                return
            except OperationalError as e:
                logger.error(f"Database connection error (attempt {attempt + 1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.error("Failed to connect to database after all retries")
                    raise

    def _get_session(self):
        """Get a new database session with retry logic."""
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                return self.Session()
            except OperationalError as e:
                logger.error(f"Session creation error (attempt {attempt + 1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    # Try to reinitialize connection
                    self._initialize_connection(max_retries=1, retry_delay=1)
                else:
                    raise

    def _execute_with_retry(self, func, *args, **kwargs):
        """Execute a database operation with retry logic."""
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except OperationalError as e:
                logger.error(f"Database operation error (attempt {attempt + 1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    # Try to reinitialize connection
                    self._initialize_connection(max_retries=1, retry_delay=1)
                else:
                    raise

    def _get_or_create_user(self, session, telegram_id):
        """Get existing user or create new one."""
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        if not user:
            user = User(telegram_id=telegram_id)
            session.add(user)
            session.commit()
        return user

    def set_user_goals(self, telegram_id: int, goals: dict):
        """Set or update user's nutrition goals."""
        session = self._get_session()
        try:
            user = self._get_or_create_user(session, telegram_id)
            
            # Check if goals exist
            user_goals = session.query(UserGoals).filter_by(user_id=user.id).first()
            
            if user_goals:
                # Update existing goals
                user_goals.calories = goals['calories']
                user_goals.protein = goals['protein']
                user_goals.fat = goals['fat']
                user_goals.carbs = goals['carbs']
            else:
                # Create new goals
                user_goals = UserGoals(
                    user_id=user.id,
                    calories=goals['calories'],
                    protein=goals['protein'],
                    fat=goals['fat'],
                    carbs=goals['carbs']
                )
                session.add(user_goals)
            
            session.commit()
            logger.info(f"Set goals for user {telegram_id}: {goals}")
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error setting goals for user {telegram_id}: {str(e)}")
            raise
        finally:
            session.close()

    def _sanitize_meal_description(self, description: str) -> str:
        """Sanitize meal description to prevent XSS and other attacks."""
        # Remove HTML tags
        description = re.sub(r'<[^>]+>', '', description)
        
        # Remove potentially dangerous characters
        description = description.replace(';', '')
        description = description.replace('--', '')
        description = description.replace('/*', '')
        description = description.replace('*/', '')
        
        return description.strip()

    def save_meal(self, telegram_id: int, description: str, analysis: dict):
        """Save a meal to the database."""
        session = self._get_session()
        try:
            # Validate user exists
            user = self._get_or_create_user(session, telegram_id)
            if not user:
                raise ValueError(f"User {telegram_id} not found")
            
            # Sanitize description
            safe_description = self._sanitize_meal_description(description)
            
            # Validate analysis data
            if not all(isinstance(analysis[key], (int, float)) for key in ['calories', 'protein', 'fat', 'carbs']):
                raise ValueError("Invalid analysis data format")
            
            meal = Meal(
                user_id=user.id,
                description=safe_description,
                calories=analysis['calories'],
                protein=analysis['protein'],
                fat=analysis['fat'],
                carbs=analysis['carbs']
            )
            
            session.add(meal)
            session.commit()
            logger.info(f"Saved meal for user {telegram_id}: {safe_description}")
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving meal for user {telegram_id}: {str(e)}")
            raise
        finally:
            session.close()

    def get_user_progress(self, telegram_id: int) -> dict:
        """Get user's current progress towards their goals."""
        session = self._get_session()
        try:
            # Validate user exists
            user = self._get_or_create_user(session, telegram_id)
            if not user:
                raise ValueError(f"User {telegram_id} not found")
            
            # Get user's goals
            goals = session.query(UserGoals).filter_by(user_id=user.id).first()
            if not goals:
                return None
            
            # Get today's meals
            today = datetime.utcnow().date()
            meals = session.query(Meal).filter(
                and_(
                    Meal.user_id == user.id,
                    func.date(Meal.created_at) == today
                )
            ).all()
            
            # Calculate totals
            total_calories = sum(meal.calories for meal in meals)
            total_protein = sum(meal.protein for meal in meals)
            total_fat = sum(meal.fat for meal in meals)
            total_carbs = sum(meal.carbs for meal in meals)
            
            progress = {
                'calories': total_calories,
                'protein': total_protein,
                'fat': total_fat,
                'carbs': total_carbs,
                'goal_calories': goals.calories,
                'goal_protein': goals.protein,
                'goal_fat': goals.fat,
                'goal_carbs': goals.carbs
            }
            
            logger.info(f"Retrieved progress for user {telegram_id}: {progress}")
            return progress
            
        except Exception as e:
            logger.error(f"Error retrieving progress for user {telegram_id}: {str(e)}")
            raise
        finally:
            session.close()

    def get_today_meals(self, telegram_id: int) -> list:
        """Get all meals logged today."""
        session = self._get_session()
        try:
            user = self._get_or_create_user(session, telegram_id)
            
            today = datetime.utcnow().date()
            meals = session.query(Meal).filter(
                and_(
                    Meal.user_id == user.id,
                    func.date(Meal.created_at) == today
                )
            ).order_by(Meal.created_at).all()
            
            result = [
                (meal.description, meal.calories, meal.protein, meal.fat, meal.carbs)
                for meal in meals
            ]
            
            logger.info(f"Retrieved {len(result)} meals for user {telegram_id}")
            return result
            
        except Exception as e:
            logger.error(f"Error retrieving today's meals for user {telegram_id}: {str(e)}")
            raise
        finally:
            session.close()

    def get_weekly_summary(self, telegram_id: int) -> list:
        """Get weekly calorie summary with goal achievement information."""
        session = self._get_session()
        try:
            user = self._get_or_create_user(session, telegram_id)
            
            # Get user's goals
            goals = session.query(UserGoals).filter_by(user_id=user.id).first()
            if not goals:
                return None
            
            # Get date range (last 7 days)
            end_date = datetime.utcnow().date()
            start_date = end_date - timedelta(days=6)
            
            # Query daily totals with all nutritional values
            daily_totals = session.query(
                func.date(Meal.created_at).label('date'),
                func.sum(Meal.calories).label('total_calories'),
                func.sum(Meal.protein).label('total_protein'),
                func.sum(Meal.fat).label('total_fat'),
                func.sum(Meal.carbs).label('total_carbs')
            ).filter(
                and_(
                    Meal.user_id == user.id,
                    func.date(Meal.created_at) >= start_date,
                    func.date(Meal.created_at) <= end_date
                )
            ).group_by(
                func.date(Meal.created_at)
            ).order_by(
                desc(func.date(Meal.created_at))
            ).all()
            
            # Format results with goal achievement information
            result = []
            for day in daily_totals:
                day_data = {
                    'date': day.date,
                    'calories': day.total_calories or 0,
                    'protein': day.total_protein or 0,
                    'fat': day.total_fat or 0,
                    'carbs': day.total_carbs or 0,
                    'goal_calories': goals.calories,
                    'goal_protein': goals.protein,
                    'goal_fat': goals.fat,
                    'goal_carbs': goals.carbs,
                    'reached_goals': {
                        'calories': (day.total_calories or 0) >= goals.calories,
                        'protein': (day.total_protein or 0) >= goals.protein,
                        'fat': (day.total_fat or 0) >= goals.fat,
                        'carbs': (day.total_carbs or 0) >= goals.carbs
                    }
                }
                result.append(day_data)
            
            logger.info(f"Retrieved weekly summary for user {telegram_id}")
            return result
            
        except Exception as e:
            logger.error(f"Error retrieving weekly summary for user {telegram_id}: {str(e)}")
            raise
        finally:
            session.close() 