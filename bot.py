import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from dotenv import load_dotenv
from database import Database
from food_analyzer import FoodAnalyzer
from goals_manager import GoalsManager

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Get environment variables
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN environment variable is not set")

# Debug environment variables
print("Environment variables:")
print(f"TELEGRAM_TOKEN: {TELEGRAM_TOKEN}")
print(f"DB_USER: {os.getenv('DB_USER')}")
print(f"DB_PASSWORD: {os.getenv('DB_PASSWORD')}")
print(f"DB_NAME: {os.getenv('DB_NAME')}")
print(f"DB_HOST: {os.getenv('DB_HOST')}")
print(f"DB_PORT: {os.getenv('DB_PORT')}")

class FoodTrackerBot:
    def __init__(self):
        self.db = Database()
        self.food_analyzer = FoodAnalyzer()
        self.goals_manager = GoalsManager()

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a message when the command /start is issued."""
        user = update.effective_user
        await update.message.reply_text(
            f'Привет, {user.first_name}! Я помогу тебе отслеживать твое питание.\n\n'
            'Доступные команды:\n'
            '/set_goals - Установить цели по питанию\n'
            '/add_meal - Добавить прием пищи\n'
            '/today - Просмотреть сегодняшние приемы пищи\n'
            '/progress - Просмотреть прогресс\n'
            '/help - Показать справку'
        )

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a message when the command /help is issued."""
        help_text = (
            'Я бот для отслеживания питания. Вот что я умею:\n\n'
            '/set_goals - Установить цели по питанию\n'
            '/add_meal - Добавить прием пищи\n'
            '/today - Просмотреть сегодняшние приемы пищи\n'
            '/progress - Просмотреть прогресс\n'
            '/help - Показать эту справку'
        )
        await update.message.reply_text(help_text)

    async def set_goals(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /set_goals command."""
        keyboard = [
            [
                InlineKeyboardButton("Похудение", callback_data='goal_weight_loss'),
                InlineKeyboardButton("Набор массы", callback_data='goal_muscle_gain'),
            ],
            [
                InlineKeyboardButton("Поддержание формы", callback_data='goal_maintenance'),
                InlineKeyboardButton("Кето-диета", callback_data='goal_keto'),
            ],
            [
                InlineKeyboardButton("Свои цели", callback_data='goal_custom'),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text('Выберите цель:', reply_markup=reply_markup)

    async def add_meal(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /add_meal command."""
        await update.message.reply_text(
            'Опишите, что вы съели. Например: "миска овсянки с бананом и орехами"'
        )

    async def handle_meal_description(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle meal description input."""
        description = update.message.text
        user_id = update.effective_user.id
        
        # Analyze the meal using OpenAI
        analysis = await self.food_analyzer.analyze_meal(description)
        
        # Save to database
        self.db.save_meal(user_id, description, analysis)
        
        # Send response
        response = (
            f'Прием пищи сохранен!\n\n'
            f'Калории: {analysis["calories"]}\n'
            f'Белки: {analysis["protein"]}г\n'
            f'Жиры: {analysis["fat"]}г\n'
            f'Углеводы: {analysis["carbs"]}г'
        )
        await update.message.reply_text(response)

    async def today(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /today command."""
        user_id = update.effective_user.id
        meals = self.db.get_today_meals(user_id)
        
        if not meals:
            await update.message.reply_text('Сегодня вы еще не добавили приемы пищи.')
            return
        
        response = 'Сегодняшние приемы пищи:\n\n'
        for meal in meals:
            response += f'• {meal[0]}\n'
            response += f'  Калории: {meal[1]}\n'
            response += f'  Б/Ж/У: {meal[2]}/{meal[3]}/{meal[4]}г\n\n'
        
        await update.message.reply_text(response)

    async def progress(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /progress command."""
        user_id = update.effective_user.id
        progress_data = self.db.get_user_progress(user_id)
        
        if not progress_data:
            await update.message.reply_text('У вас пока нет данных о прогрессе.')
            return
        
        response = (
            f'Ваш прогресс:\n\n'
            f'Калории: {progress_data["calories"]}/{progress_data["goal_calories"]}\n'
            f'Белки: {progress_data["protein"]}/{progress_data["goal_protein"]}г\n'
            f'Жиры: {progress_data["fat"]}/{progress_data["goal_fat"]}г\n'
            f'Углеводы: {progress_data["carbs"]}/{progress_data["goal_carbs"]}г'
        )
        await update.message.reply_text(response)

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks."""
        query = update.callback_query
        await query.answer()
        
        if query.data.startswith('goal_'):
            goal_type = query.data[5:]  # Remove 'goal_' prefix
            await self.handle_goal_selection(update, context, goal_type)

    async def handle_goal_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE, goal_type: str):
        """Handle goal selection."""
        user_id = update.effective_user.id
        
        if goal_type == 'custom':
            await update.callback_query.message.reply_text(
                'Введите свои цели в формате:\n'
                'калории белки жиры углеводы\n'
                'Например: 2000 150 60 200'
            )
            return
        
        # Set predefined goals
        goals = self.goals_manager.get_predefined_goals(goal_type)
        self.db.set_user_goals(user_id, goals)
        
        await update.callback_query.message.reply_text(
            f'Цели установлены!\n\n'
            f'Калории: {goals["calories"]}\n'
            f'Белки: {goals["protein"]}г\n'
            f'Жиры: {goals["fat"]}г\n'
            f'Углеводы: {goals["carbs"]}г'
        )

def main():
    """Start the bot."""
    # Create the Application and pass it your bot's token
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    bot = FoodTrackerBot()
    
    # Add handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("help", bot.help))
    application.add_handler(CommandHandler("set_goals", bot.set_goals))
    application.add_handler(CommandHandler("add_meal", bot.add_meal))
    application.add_handler(CommandHandler("today", bot.today))
    application.add_handler(CommandHandler("progress", bot.progress))
    
    # Add message handler for meal descriptions
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_meal_description))
    
    # Add callback query handler
    application.add_handler(CallbackQueryHandler(bot.button_callback))
    
    # Start the Bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main() 