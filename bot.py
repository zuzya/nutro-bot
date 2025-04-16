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
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Get environment variables
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN environment variable is not set")

# Debug environment variables
logger.info("Environment variables loaded:")
logger.info(f"TELEGRAM_TOKEN: {TELEGRAM_TOKEN}")
logger.info(f"DB_USER: {os.getenv('DB_USER')}")
logger.info(f"DB_PASSWORD: {os.getenv('DB_PASSWORD')}")
logger.info(f"DB_NAME: {os.getenv('DB_NAME')}")
logger.info(f"DB_HOST: {os.getenv('DB_HOST')}")
logger.info(f"DB_PORT: {os.getenv('DB_PORT')}")

class FoodTrackerBot:
    def __init__(self):
        """Initialize the bot."""
        # Initialize the bot with your token
        self.application = Application.builder().token(os.getenv('TELEGRAM_TOKEN')).build()
        
        # Add command handlers
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help))
        self.application.add_handler(CommandHandler("set_goals", self.set_goals))
        self.application.add_handler(CommandHandler("add_meal", self.add_meal))
        self.application.add_handler(CommandHandler("today", self.today))
        self.application.add_handler(CommandHandler("weekly", self.weekly))
        self.application.add_handler(CommandHandler("recommendations", self.recommendations))
        self.application.add_handler(CommandHandler("menu", self.show_main_menu))
        
        # Add message handler for meal descriptions
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_meal_description))
        
        # Add callback query handler for buttons
        self.application.add_handler(CallbackQueryHandler(self.button_callback))
        
        # Initialize database and food analyzer
        self.db = Database()
        self.food_analyzer = FoodAnalyzer()
        self.goals_manager = GoalsManager()
        logger.info("Bot initialized with all services")

    async def show_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, is_callback: bool = False):
        """Show the main menu with all available options."""
        user = update.effective_user
        logger.info(f"Showing main menu for user {user.id}")
        
        # Get current progress
        try:
            progress_data = self.db.get_user_progress(user.id)
            logger.info(f"Retrieved progress data for user {user.id}: {progress_data}")
            
            if progress_data:
                progress_text = (
                    f'📊 Ваш текущий прогресс:\n\n'
                    f'• Калории: {progress_data["calories"]}/{progress_data["goal_calories"]}\n'
                    f'• Белки: {progress_data["protein"]}/{progress_data["goal_protein"]}г\n'
                    f'• Жиры: {progress_data["fat"]}/{progress_data["goal_fat"]}г\n'
                    f'• Углеводы: {progress_data["carbs"]}/{progress_data["goal_carbs"]}г\n\n'
                )
            else:
                progress_text = '📝 Вы еще не установили цели по питанию.\n\n'
        except Exception as e:
            logger.error(f"Error retrieving progress for user {user.id}: {str(e)}")
            progress_text = '⚠️ Не удалось получить информацию о вашем прогрессе.\n\n'
        
        keyboard = [
            [
                InlineKeyboardButton("📅 Сегодняшние приемы пищи", callback_data='today'),
                InlineKeyboardButton("📈 Недельная статистика", callback_data='weekly'),
            ],
            [
                InlineKeyboardButton("💡 Получить рекомендации", callback_data='recommendations'),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = (
            f'👋 Привет, {user.first_name}! Я помогу вам отслеживать ваше питание.\n\n'
            f'{progress_text}'
            'Что бы вы хотели сделать?\n\n'
            'Доступные команды:\n'
            '/set_goals - Установить цели по питанию\n'
            '/menu - Показать это меню\n'
            '/help - Показать справку\n\n'
            'Чтобы добавить прием пищи, просто напишите, что вы съели.'
        )
        
        if is_callback:
            await update.callback_query.message.edit_text(message, reply_markup=reply_markup)
        else:
            await update.message.reply_text(message, reply_markup=reply_markup)

    async def handle_meal_description(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle meal description input."""
        user = update.effective_user
        description = update.message.text
        logger.info(f"User {user.id} submitted meal description: {description}")
        
        try:
            # Analyze the meal using OpenAI
            logger.info(f"Starting meal analysis for user {user.id}")
            analysis = await self.food_analyzer.analyze_meal(description)
            logger.info(f"Meal analysis completed for user {user.id}: {analysis}")
            
            # Save to database
            logger.info(f"Saving meal to database for user {user.id}")
            self.db.save_meal(user.id, description, analysis)
            
            # Get current progress and goals
            progress_data = self.db.get_user_progress(user.id)
            logger.info(f"Retrieved progress data for user {user.id}: {progress_data}")
            
            # Calculate remaining values
            if progress_data:
                remaining = {
                    'calories': progress_data['goal_calories'] - progress_data['calories'],
                    'protein': progress_data['goal_protein'] - progress_data['protein'],
                    'fat': progress_data['goal_fat'] - progress_data['fat'],
                    'carbs': progress_data['goal_carbs'] - progress_data['carbs']
                }
                logger.info(f"Calculated remaining targets for user {user.id}: {remaining}")
            else:
                remaining = None
                logger.info(f"No progress data available for user {user.id}")
            
            # Get feedback from LLM
            feedback_prompt = (
                f"Пользователь только что залогировал прием пищи: {description}\n"
                f"Питательная ценность: {analysis}\n"
                f"Текущие дневные итоги: {progress_data if progress_data else 'Цели не установлены'}\n"
                f"Оставшиеся дневные цели: {remaining if remaining else 'Н/Д'}\n\n"
                "Дайте краткий, дружелюбный отзыв об этом приеме пищи в контексте дневных целей. "
                "Включите простое сравнение питательных веществ приема пищи с оставшимися дневными целями. "
                "Будьте краткими и ободряющими."
            )
            
            logger.info(f"Requesting feedback from LLM for user {user.id}")
            feedback = await self.food_analyzer.get_feedback(feedback_prompt)
            logger.info(f"Received feedback from LLM for user {user.id}: {feedback}")
            
            # Prepare response
            response = (
                f'✅ Прием пищи сохранен!\n\n'
                f'📊 Этот прием пищи:\n'
                f'• Калории: {analysis["calories"]}\n'
                f'• Белки: {analysis["protein"]}г\n'
                f'• Жиры: {analysis["fat"]}г\n'
                f'• Углеводы: {analysis["carbs"]}г\n\n'
            )
            
            if progress_data:
                response += (
                    f'📈 Сегодняшние итоги:\n'
                    f'• Калории: {progress_data["calories"]}/{progress_data["goal_calories"]}\n'
                    f'• Белки: {progress_data["protein"]}/{progress_data["goal_protein"]}г\n'
                    f'• Жиры: {progress_data["fat"]}/{progress_data["goal_fat"]}г\n'
                    f'• Углеводы: {progress_data["carbs"]}/{progress_data["goal_carbs"]}г\n\n'
                )
                
                if remaining:
                    response += (
                        f'🎯 Осталось на сегодня:\n'
                        f'• Калории: {remaining["calories"]}\n'
                        f'• Белки: {remaining["protein"]}г\n'
                        f'• Жиры: {remaining["fat"]}г\n'
                        f'• Углеводы: {remaining["carbs"]}г\n\n'
                    )
            
            response += f'💬 Отзыв:\n{feedback}'
            
            keyboard = [[InlineKeyboardButton("🔙 В главное меню", callback_data='main_menu')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(response, reply_markup=reply_markup)
            logger.info(f"Response sent to user {user.id}")
            
        except Exception as e:
            logger.error(f"Error processing meal for user {user.id}: {str(e)}")
            keyboard = [[InlineKeyboardButton("🔙 В главное меню", callback_data='main_menu')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text('⚠️ К сожалению, произошла ошибка при обработке вашего приема пищи. Пожалуйста, попробуйте еще раз.', reply_markup=reply_markup)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a message when the command /start is issued."""
        user = update.effective_user
        logger.info(f"User {user.id} ({user.first_name}) started the bot")
        
        await self.show_main_menu(update, context)

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a message when the command /help is issued."""
        user = update.effective_user
        logger.info(f"User {user.id} requested help")
        
        # Get current progress
        try:
            progress_data = self.db.get_user_progress(user.id)
            logger.info(f"Retrieved progress data for user {user.id}: {progress_data}")
            
            if progress_data:
                progress_text = (
                    f'\n📊 Ваш текущий прогресс:\n'
                    f'• Калории: {progress_data["calories"]}/{progress_data["goal_calories"]}\n'
                    f'• Белки: {progress_data["protein"]}/{progress_data["goal_protein"]}г\n'
                    f'• Жиры: {progress_data["fat"]}/{progress_data["goal_fat"]}г\n'
                    f'• Углеводы: {progress_data["carbs"]}/{progress_data["goal_carbs"]}г\n'
                )
            else:
                progress_text = '\n📝 Вы еще не установили цели по питанию.\n'
        except Exception as e:
            logger.error(f"Error retrieving progress for user {user.id}: {str(e)}")
            progress_text = '\n⚠️ Не удалось получить информацию о вашем прогрессе.\n'
        
        keyboard = [
            [
                InlineKeyboardButton("📅 Сегодняшние приемы пищи", callback_data='today'),
                InlineKeyboardButton("📈 Недельная статистика", callback_data='weekly'),
            ],
            [
                InlineKeyboardButton("💡 Получить рекомендации", callback_data='recommendations'),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        help_text = (
            'Я бот для отслеживания питания. Вот что я умею:\n\n'
            '/set_goals - Установить цели по питанию\n'
            '/today - Посмотреть сегодняшние приемы пищи\n'
            '/weekly - Посмотреть недельную статистику\n'
            '/recommendations - Получить персонализированные рекомендации\n'
            '/menu - Показать главное меню\n'
            '/help - Показать эту справку\n\n'
            'Чтобы добавить прием пищи, просто напишите, что вы съели.\n'
            'Например: "тарелка овсянки с бананом и орехами"'
        )
        await update.message.reply_text(help_text + progress_text, reply_markup=reply_markup)

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks."""
        query = update.callback_query
        user = update.effective_user
        logger.info(f"User {user.id} pressed button: {query.data}")
        
        await query.answer()
        
        if query.data == 'main_menu':
            await self.show_main_menu(update, context, is_callback=True)
        elif query.data == 'set_goals':
            await self.set_goals(update, context, is_callback=True)
        elif query.data == 'add_meal':
            await self.add_meal(update, context, is_callback=True)
        elif query.data == 'today':
            await self.today(update, context, is_callback=True)
        elif query.data == 'weekly':
            await self.weekly(update, context, is_callback=True)
        elif query.data == 'recommendations':
            await self.recommendations(update, context, is_callback=True)
        elif query.data.startswith('goal_'):
            goal_type = query.data[5:]  # Remove 'goal_' prefix
            await self.handle_goal_selection(update, context, goal_type)

    async def handle_goal_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE, goal_type: str):
        """Handle goal selection."""
        user = update.effective_user
        logger.info(f"User {user.id} selected goal type: {goal_type}")
        
        if goal_type == 'custom':
            message = (
                'Enter your goals in the format:\n'
                'calories protein fat carbs\n'
                'For example: 2000 150 60 200'
            )
            await update.callback_query.message.reply_text(message)
            return
        
        try:
            # Set predefined goals
            goals = self.goals_manager.get_predefined_goals(goal_type)
            self.db.set_user_goals(user.id, goals)
            logger.info(f"Set goals for user {user.id}: {goals}")
            
            response = (
                f'Goals set!\n\n'
                f'Calories: {goals["calories"]}\n'
                f'Protein: {goals["protein"]}g\n'
                f'Fat: {goals["fat"]}g\n'
                f'Carbs: {goals["carbs"]}g'
            )
            await update.callback_query.message.reply_text(response)
            logger.info(f"Sent goal confirmation to user {user.id}")
            
        except Exception as e:
            logger.error(f"Error setting goals for user {user.id}: {str(e)}")
            await update.callback_query.message.reply_text(
                'Sorry, there was an error setting your goals. Please try again.'
            )

    async def set_goals(self, update: Update, context: ContextTypes.DEFAULT_TYPE, is_callback: bool = False):
        """Handle the /set_goals command."""
        user = update.effective_user
        logger.info(f"User {user.id} requested to set goals")
        
        keyboard = [
            [
                InlineKeyboardButton("📉 Похудение", callback_data='goal_weight_loss'),
                InlineKeyboardButton("📈 Набор массы", callback_data='goal_muscle_gain'),
            ],
            [
                InlineKeyboardButton("⚖️ Поддержание", callback_data='goal_maintenance'),
                InlineKeyboardButton("✏️ Свои цели", callback_data='goal_custom'),
            ],
            [
                InlineKeyboardButton("🔙 В главное меню", callback_data='main_menu'),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = 'Выберите вашу цель:'
        if is_callback:
            await update.callback_query.message.edit_text(message, reply_markup=reply_markup)
        else:
            await update.message.reply_text(message, reply_markup=reply_markup)

    async def add_meal(self, update: Update, context: ContextTypes.DEFAULT_TYPE, is_callback: bool = False):
        """Handle the /add_meal command."""
        user = update.effective_user
        logger.info(f"User {user.id} requested to add a meal")
        
        keyboard = [[InlineKeyboardButton("🔙 В главное меню", callback_data='main_menu')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = (
            'Опишите, что вы съели.\n\n'
            'Например: "тарелка овсянки с бананом и орехами"'
        )
        if is_callback:
            await update.callback_query.message.edit_text(message, reply_markup=reply_markup)
        else:
            await update.message.reply_text(message, reply_markup=reply_markup)

    async def today(self, update: Update, context: ContextTypes.DEFAULT_TYPE, is_callback: bool = False):
        """Handle the /today command."""
        user = update.effective_user
        logger.info(f"User {user.id} requested today's meals")
        
        try:
            meals = self.db.get_today_meals(user.id)
            logger.info(f"Retrieved {len(meals)} meals for user {user.id}")
            
            keyboard = [[InlineKeyboardButton("🔙 В главное меню", callback_data='main_menu')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if not meals:
                message = '📝 Вы еще не добавили приемы пищи сегодня.'
                if is_callback:
                    await update.callback_query.message.edit_text(message, reply_markup=reply_markup)
                else:
                    await update.message.reply_text(message, reply_markup=reply_markup)
                return
            
            response = '🍽 Сегодняшние приемы пищи:\n\n'
            for meal in meals:
                response += f'• {meal[0]}\n'
                response += f'  Калории: {meal[1]}\n'
                response += f'  Б/Ж/У: {meal[2]}/{meal[3]}/{meal[4]}г\n\n'
            
            if is_callback:
                await update.callback_query.message.edit_text(response, reply_markup=reply_markup)
            else:
                await update.message.reply_text(response, reply_markup=reply_markup)
            logger.info(f"Today's meals sent to user {user.id}")
            
        except Exception as e:
            logger.error(f"Error retrieving today's meals for user {user.id}: {str(e)}")
            error_message = '⚠️ К сожалению, произошла ошибка при получении ваших приемов пищи. Пожалуйста, попробуйте еще раз.'
            keyboard = [[InlineKeyboardButton("🔙 В главное меню", callback_data='main_menu')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            if is_callback:
                await update.callback_query.message.edit_text(error_message, reply_markup=reply_markup)
            else:
                await update.message.reply_text(error_message, reply_markup=reply_markup)

    async def weekly(self, update: Update, context: ContextTypes.DEFAULT_TYPE, is_callback: bool = False):
        """Handle the /weekly command."""
        user = update.effective_user
        logger.info(f"User {user.id} requested weekly summary")
        
        try:
            weekly_data = self.db.get_weekly_summary(user.id)
            logger.info(f"Retrieved weekly data for user {user.id}: {weekly_data}")
            
            keyboard = [[InlineKeyboardButton("🔙 В главное меню", callback_data='main_menu')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if not weekly_data:
                message = '📝 Вы не залогировали приемы пищи за последние 7 дней.'
                if is_callback:
                    await update.callback_query.message.edit_text(message, reply_markup=reply_markup)
                else:
                    await update.message.reply_text(message, reply_markup=reply_markup)
                return
            
            response = '📊 Ваше потребление калорий за последние 7 дней:\n\n'
            for day in weekly_data:
                date_str = day[0].strftime('%Y-%m-%d')
                calories = day[1] or 0
                response += f'• {date_str}: {calories} калорий\n'
            
            # Calculate average
            total_calories = sum(day[1] or 0 for day in weekly_data)
            avg_calories = total_calories / len(weekly_data)
            response += f'\n📈 Среднее дневное потребление: {avg_calories:.0f} калорий'
            
            if is_callback:
                await update.callback_query.message.edit_text(response, reply_markup=reply_markup)
            else:
                await update.message.reply_text(response, reply_markup=reply_markup)
            logger.info(f"Weekly summary sent to user {user.id}")
            
        except Exception as e:
            logger.error(f"Error retrieving weekly summary for user {user.id}: {str(e)}")
            error_message = '⚠️ К сожалению, произошла ошибка при получении вашей недельной статистики. Пожалуйста, попробуйте еще раз.'
            keyboard = [[InlineKeyboardButton("🔙 В главное меню", callback_data='main_menu')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            if is_callback:
                await update.callback_query.message.edit_text(error_message, reply_markup=reply_markup)
            else:
                await update.message.reply_text(error_message, reply_markup=reply_markup)

    async def recommendations(self, update: Update, context: ContextTypes.DEFAULT_TYPE, is_callback: bool = False):
        """Handle the /recommendations command."""
        user = update.effective_user
        logger.info(f"User {user.id} requested recommendations")
        
        try:
            # Get current progress
            progress_data = self.db.get_user_progress(user.id)
            if not progress_data:
                keyboard = [[InlineKeyboardButton("🔙 В главное меню", callback_data='main_menu')]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                message = '📝 Пожалуйста, сначала установите цели по питанию, чтобы получить персонализированные рекомендации.'
                logger.info(f"No goals set for user {user.id}, cannot generate recommendations")
                if is_callback:
                    await update.callback_query.message.edit_text(message, reply_markup=reply_markup)
                else:
                    await update.message.reply_text(message, reply_markup=reply_markup)
                return
            
            # Calculate remaining values
            remaining = {
                'calories': progress_data['goal_calories'] - progress_data['calories'],
                'protein': progress_data['goal_protein'] - progress_data['protein'],
                'fat': progress_data['goal_fat'] - progress_data['fat'],
                'carbs': progress_data['goal_carbs'] - progress_data['carbs']
            }
            logger.info(f"Calculated remaining targets for user {user.id}: {remaining}")
            
            # Get recommendations from LLM
            logger.info(f"Requesting recommendations from LLM for user {user.id}")
            recommendations = await self.food_analyzer.get_recommendations(progress_data, remaining)
            logger.info(f"Received recommendations from LLM for user {user.id}: {recommendations}")
            
            # Prepare response
            response = (
                f'📊 На основе вашего текущего прогресса:\n\n'
                f'• Калории: {progress_data["calories"]}/{progress_data["goal_calories"]}\n'
                f'• Белки: {progress_data["protein"]}/{progress_data["goal_protein"]}г\n'
                f'• Жиры: {progress_data["fat"]}/{progress_data["goal_fat"]}г\n'
                f'• Углеводы: {progress_data["carbs"]}/{progress_data["goal_carbs"]}г\n\n'
                f'💡 Вот несколько рекомендаций для вашего следующего приема пищи:\n\n'
                f'{recommendations}'
            )
            
            keyboard = [[InlineKeyboardButton("🔙 В главное меню", callback_data='main_menu')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if is_callback:
                await update.callback_query.message.edit_text(response, reply_markup=reply_markup)
            else:
                await update.message.reply_text(response, reply_markup=reply_markup)
            logger.info(f"Recommendations sent to user {user.id}")
            
        except Exception as e:
            logger.error(f"Error generating recommendations for user {user.id}: {str(e)}")
            error_message = '⚠️ К сожалению, произошла ошибка при генерации рекомендаций. Пожалуйста, попробуйте еще раз.'
            keyboard = [[InlineKeyboardButton("🔙 В главное меню", callback_data='main_menu')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            if is_callback:
                await update.callback_query.message.edit_text(error_message, reply_markup=reply_markup)
            else:
                await update.message.reply_text(error_message, reply_markup=reply_markup)

def main():
    """Start the bot."""
    logger.info("Starting bot...")
    
    # Create the Application and pass it your bot's token
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    bot = FoodTrackerBot()
    
    # Add handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("help", bot.help))
    application.add_handler(CommandHandler("set_goals", bot.set_goals))
    application.add_handler(CommandHandler("add_meal", bot.add_meal))
    application.add_handler(CommandHandler("today", bot.today))
    application.add_handler(CommandHandler("weekly", bot.weekly))
    application.add_handler(CommandHandler("recommendations", bot.recommendations))
    
    # Add message handler for meal descriptions
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_meal_description))
    
    # Add callback query handler for inline buttons
    application.add_handler(CallbackQueryHandler(bot.button_callback))
    
    # Start the Bot
    logger.info("Bot is running and polling for updates...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main() 