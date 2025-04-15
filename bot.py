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
                    f'Your current progress:\n'
                    f'Calories: {progress_data["calories"]}/{progress_data["goal_calories"]}\n'
                    f'Protein: {progress_data["protein"]}/{progress_data["goal_protein"]}g\n'
                    f'Fat: {progress_data["fat"]}/{progress_data["goal_fat"]}g\n'
                    f'Carbs: {progress_data["carbs"]}/{progress_data["goal_carbs"]}g\n\n'
                )
            else:
                progress_text = 'You haven\'t set any goals yet.\n\n'
        except Exception as e:
            logger.error(f"Error retrieving progress for user {user.id}: {str(e)}")
            progress_text = 'Unable to retrieve your progress at the moment.\n\n'
        
        keyboard = [
            [
                InlineKeyboardButton("Set Goals", callback_data='set_goals'),
                InlineKeyboardButton("Add Meal", callback_data='add_meal'),
            ],
            [
                InlineKeyboardButton("Today's Meals", callback_data='today'),
                InlineKeyboardButton("Weekly Summary", callback_data='weekly'),
            ],
            [
                InlineKeyboardButton("Get Recommendations", callback_data='recommendations'),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = (
            f'Hi {user.first_name}! I will help you track your nutrition.\n\n'
            f'{progress_text}'
            'What would you like to do?\n\n'
            'Available commands:\n'
            '/set_goals - Set nutrition goals\n'
            '/add_meal - Add a meal\n'
            '/today - View today\'s meals\n'
            '/weekly - View weekly calorie summary\n'
            '/recommendations - Get personalized nutrition advice\n'
            '/menu - Show this menu\n'
            '/help - Show help'
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
                f"User just logged a meal: {description}\n"
                f"Nutritional content: {analysis}\n"
                f"Current daily totals: {progress_data if progress_data else 'No goals set'}\n"
                f"Remaining daily targets: {remaining if remaining else 'N/A'}\n\n"
                "Provide a brief, friendly feedback about this meal in the context of their daily goals. "
                "Include a simple comparison of the meal's nutrients vs remaining daily targets. "
                "Keep it concise and encouraging."
            )
            
            logger.info(f"Requesting feedback from LLM for user {user.id}")
            feedback = await self.food_analyzer.get_feedback(feedback_prompt)
            logger.info(f"Received feedback from LLM for user {user.id}: {feedback}")
            
            # Prepare response
            response = (
                f'Meal saved!\n\n'
                f'This meal:\n'
                f'Calories: {analysis["calories"]}\n'
                f'Protein: {analysis["protein"]}g\n'
                f'Fat: {analysis["fat"]}g\n'
                f'Carbs: {analysis["carbs"]}g\n\n'
            )
            
            if progress_data:
                response += (
                    f'Today\'s totals:\n'
                    f'Calories: {progress_data["calories"]}/{progress_data["goal_calories"]}\n'
                    f'Protein: {progress_data["protein"]}/{progress_data["goal_protein"]}g\n'
                    f'Fat: {progress_data["fat"]}/{progress_data["goal_fat"]}g\n'
                    f'Carbs: {progress_data["carbs"]}/{progress_data["goal_carbs"]}g\n\n'
                )
                
                if remaining:
                    response += (
                        f'Remaining for today:\n'
                        f'Calories: {remaining["calories"]}\n'
                        f'Protein: {remaining["protein"]}g\n'
                        f'Fat: {remaining["fat"]}g\n'
                        f'Carbs: {remaining["carbs"]}g\n\n'
                    )
            
            response += f'Feedback:\n{feedback}'
            
            keyboard = [[InlineKeyboardButton("Back to Main Menu", callback_data='main_menu')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(response, reply_markup=reply_markup)
            logger.info(f"Response sent to user {user.id}")
            
        except Exception as e:
            logger.error(f"Error processing meal for user {user.id}: {str(e)}")
            keyboard = [[InlineKeyboardButton("Back to Main Menu", callback_data='main_menu')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text('Sorry, there was an error processing your meal. Please try again.', reply_markup=reply_markup)

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
                    f'\nYour current progress:\n'
                    f'Calories: {progress_data["calories"]}/{progress_data["goal_calories"]}\n'
                    f'Protein: {progress_data["protein"]}/{progress_data["goal_protein"]}g\n'
                    f'Fat: {progress_data["fat"]}/{progress_data["goal_fat"]}g\n'
                    f'Carbs: {progress_data["carbs"]}/{progress_data["goal_carbs"]}g\n'
                )
            else:
                progress_text = '\nYou haven\'t set any goals yet.\n'
        except Exception as e:
            logger.error(f"Error retrieving progress for user {user.id}: {str(e)}")
            progress_text = '\nUnable to retrieve your progress at the moment.\n'
        
        keyboard = [
            [
                InlineKeyboardButton("Set Goals", callback_data='set_goals'),
                InlineKeyboardButton("Add Meal", callback_data='add_meal'),
            ],
            [
                InlineKeyboardButton("Today's Meals", callback_data='today'),
                InlineKeyboardButton("Weekly Summary", callback_data='weekly'),
            ],
            [
                InlineKeyboardButton("Get Recommendations", callback_data='recommendations'),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        help_text = (
            'I am a nutrition tracking bot. Here\'s what I can do:\n\n'
            '/set_goals - Set your nutrition goals\n'
            '/add_meal - Add a meal\n'
            '/today - View today\'s meals\n'
            '/weekly - View weekly calorie summary\n'
            '/recommendations - Get personalized nutrition advice\n'
            '/help - Show this help message'
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
                InlineKeyboardButton("Weight Loss", callback_data='goal_weight_loss'),
                InlineKeyboardButton("Muscle Gain", callback_data='goal_muscle_gain'),
            ],
            [
                InlineKeyboardButton("Maintenance", callback_data='goal_maintenance'),
                InlineKeyboardButton("Custom", callback_data='goal_custom'),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = 'Choose your goal:'
        if is_callback:
            await update.callback_query.message.reply_text(message, reply_markup=reply_markup)
        else:
            await update.message.reply_text(message, reply_markup=reply_markup)

    async def add_meal(self, update: Update, context: ContextTypes.DEFAULT_TYPE, is_callback: bool = False):
        """Handle the /add_meal command."""
        user = update.effective_user
        logger.info(f"User {user.id} requested to add a meal")
        
        message = 'Please describe what you ate. For example: "bowl of oatmeal with banana and nuts"'
        if is_callback:
            await update.callback_query.message.reply_text(message)
        else:
            await update.message.reply_text(message)

    async def today(self, update: Update, context: ContextTypes.DEFAULT_TYPE, is_callback: bool = False):
        """Handle the /today command."""
        user = update.effective_user
        logger.info(f"User {user.id} requested today's meals")
        
        try:
            meals = self.db.get_today_meals(user.id)
            logger.info(f"Retrieved {len(meals)} meals for user {user.id}")
            
            keyboard = [[InlineKeyboardButton("Back to Main Menu", callback_data='main_menu')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if not meals:
                message = 'You haven\'t added any meals today.'
                if is_callback:
                    await update.callback_query.message.edit_text(message, reply_markup=reply_markup)
                else:
                    await update.message.reply_text(message, reply_markup=reply_markup)
                return
            
            response = 'Today\'s meals:\n\n'
            for meal in meals:
                response += f'• {meal[0]}\n'
                response += f'  Calories: {meal[1]}\n'
                response += f'  P/F/C: {meal[2]}/{meal[3]}/{meal[4]}g\n\n'
            
            if is_callback:
                await update.callback_query.message.edit_text(response, reply_markup=reply_markup)
            else:
                await update.message.reply_text(response, reply_markup=reply_markup)
            logger.info(f"Today's meals sent to user {user.id}")
            
        except Exception as e:
            logger.error(f"Error retrieving today's meals for user {user.id}: {str(e)}")
            error_message = 'Sorry, there was an error retrieving your meals. Please try again.'
            keyboard = [[InlineKeyboardButton("Back to Main Menu", callback_data='main_menu')]]
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
            
            keyboard = [[InlineKeyboardButton("Back to Main Menu", callback_data='main_menu')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if not weekly_data:
                message = 'You haven\'t logged any meals in the last 7 days.'
                if is_callback:
                    await update.callback_query.message.edit_text(message, reply_markup=reply_markup)
                else:
                    await update.message.reply_text(message, reply_markup=reply_markup)
                return
            
            response = 'Your calorie intake for the last 7 days:\n\n'
            for day in weekly_data:
                date_str = day[0].strftime('%Y-%m-%d')
                calories = day[1] or 0
                response += f'{date_str}: {calories} calories\n'
            
            # Calculate average
            total_calories = sum(day[1] or 0 for day in weekly_data)
            avg_calories = total_calories / len(weekly_data)
            response += f'\nAverage daily intake: {avg_calories:.0f} calories'
            
            if is_callback:
                await update.callback_query.message.edit_text(response, reply_markup=reply_markup)
            else:
                await update.message.reply_text(response, reply_markup=reply_markup)
            logger.info(f"Weekly summary sent to user {user.id}")
            
        except Exception as e:
            logger.error(f"Error retrieving weekly summary for user {user.id}: {str(e)}")
            error_message = 'Sorry, there was an error retrieving your weekly summary. Please try again.'
            keyboard = [[InlineKeyboardButton("Back to Main Menu", callback_data='main_menu')]]
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
                keyboard = [[InlineKeyboardButton("Back to Main Menu", callback_data='main_menu')]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                message = 'Please set your nutrition goals first to get personalized recommendations.'
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
                f'Based on your current progress:\n\n'
                f'Calories: {progress_data["calories"]}/{progress_data["goal_calories"]}\n'
                f'Protein: {progress_data["protein"]}/{progress_data["goal_protein"]}g\n'
                f'Fat: {progress_data["fat"]}/{progress_data["goal_fat"]}g\n'
                f'Carbs: {progress_data["carbs"]}/{progress_data["goal_carbs"]}g\n\n'
                f'Here are some recommendations for your next meal:\n\n'
                f'{recommendations}'
            )
            
            keyboard = [[InlineKeyboardButton("Back to Main Menu", callback_data='main_menu')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if is_callback:
                await update.callback_query.message.edit_text(response, reply_markup=reply_markup)
            else:
                await update.message.reply_text(response, reply_markup=reply_markup)
            logger.info(f"Recommendations sent to user {user.id}")
            
        except Exception as e:
            logger.error(f"Error generating recommendations for user {user.id}: {str(e)}")
            error_message = 'Sorry, there was an error generating recommendations. Please try again.'
            keyboard = [[InlineKeyboardButton("Back to Main Menu", callback_data='main_menu')]]
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