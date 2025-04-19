import os
import logging
import asyncio
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from dotenv import load_dotenv
from database import Database
from food_analyzer import FoodAnalyzer
from goals_manager import GoalsManager
from telemetry import init_telemetry

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
        # Initialize telemetry
        self.telemetry = init_telemetry()
        self.logger = self.telemetry['logger']
        self.metrics = self.telemetry['metrics']
        
        # Initialize the bot with your token
        self.application = Application.builder().token(os.getenv('TELEGRAM_TOKEN')).build()
        
        # Initialize database and food analyzer
        self.db = Database()
        self.food_analyzer = FoodAnalyzer()
        self.goals_manager = GoalsManager()
        
        # Dictionary to track user states
        self.user_states = {}
        self.logger.info("Bot initialized with all services")

    async def initialize(self):
        """Initialize bot commands asynchronously."""
        commands = [                        
            BotCommand("today", "Показать лог дня"),
            BotCommand("weekly", "Показать статистику"),
            BotCommand("recommendations", "Получить рекомендации"),
            BotCommand("set_goals", "Установить цели по питанию"),
            BotCommand("help", "Показать справку"),
        ]
        await self.application.bot.set_my_commands(commands)
        self.logger.info("Bot commands initialized")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming text messages."""
        user = update.effective_user
        text = update.message.text
        
        # Check if user is in custom goals input state
        if user.id in self.user_states:
            if self.user_states[user.id] == 'waiting_for_custom_goals':
                await self.handle_custom_goals_input(update, context)
            elif self.user_states[user.id] == 'waiting_for_weight_info':
                await self.handle_weight_input(update, context)
            elif self.user_states[user.id] == 'waiting_for_activity_level':
                await self.handle_activity_level_input(update, context)
        else:
            # Handle as meal description
            await self.handle_meal_description(update, context)

    async def handle_custom_goals_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle custom goals input."""
        user = update.effective_user
        text = update.message.text
        
        try:
            # Parse the input (format: calories protein fat carbs)
            parts = text.split()
            if len(parts) != 4:
                raise ValueError("Неверный формат. Введите значения через пробел: калории белки жиры углеводы")
            
            goals = {
                'calories': int(parts[0]),
                'protein': int(parts[1]),
                'fat': int(parts[2]),
                'carbs': int(parts[3])
            }
            
            # Validate the goals
            if any(value <= 0 for value in goals.values()):
                raise ValueError("Все значения должны быть положительными числами")
            
            # Save the goals
            self.db.set_user_goals(user.id, goals)
            self.logger.info(f"Set custom goals for user {user.id}: {goals}")
            
            # Update metrics
            self.metrics['goal_counter'].inc()
            self.metrics['user_counter'].inc()
            
            # Clear the state
            del self.user_states[user.id]
            
            response = (
                f'✅ Цели установлены!\n\n'
                f'📊 Ваши цели по питанию:\n'
                f'• Калории: {goals["calories"]}\n'
                f'• Белки: {goals["protein"]}г\n'
                f'• Жиры: {goals["fat"]}г\n'
                f'• Углеводы: {goals["carbs"]}г\n\n'
                '💡 Вы можете вводить информацию о приемах пищи прямо в чат!\n'
                'Просто напишите, что вы съели, например: "тарелка овсянки с бананом и орехами"'
            )
            
            await update.message.reply_text(response)
            
        except ValueError as e:
            error_message = f'⚠️ {str(e)}\n\nПожалуйста, введите значения в формате:\nкалории белки жиры углеводы\nНапример: 2000 150 60 200'
            await update.message.reply_text(error_message)
        except Exception as e:
            self.logger.error(f"Error setting custom goals for user {user.id}: {str(e)}")
            error_message = '⚠️ К сожалению, произошла ошибка при установке целей. Пожалуйста, попробуйте еще раз.'
            await update.message.reply_text(error_message)
            del self.user_states[user.id]

    async def handle_weight_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle weight information input."""
        user = update.effective_user
        text = update.message.text
        
        try:
            # Parse current and target weight
            parts = text.split()
            if len(parts) != 2:
                raise ValueError("Неверный формат. Введите значения через пробел: текущий_вес желаемый_вес")
            
            current_weight = float(parts[0])
            target_weight = float(parts[1])
            
            # Validate the weights
            if current_weight <= 0 or target_weight <= 0:
                raise ValueError("Вес должен быть положительным числом")
            
            # Store weights in context
            context.user_data['current_weight'] = current_weight
            context.user_data['target_weight'] = target_weight
            
            # Set state to waiting for activity level
            self.user_states[user.id] = 'waiting_for_activity_level'
            
            keyboard = [
                [
                    InlineKeyboardButton("🪑 Малоподвижный", callback_data='activity_sedentary'),
                ],
                [
                    InlineKeyboardButton("🏃 Умеренная активность", callback_data='activity_moderate'),
                ],
                [
                    InlineKeyboardButton("🏋️ Высокая активность", callback_data='activity_active'),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            message = (
                'Выберите ваш уровень физической активности:\n\n'
                '🪑 Малоподвижный - сидячая работа, мало движения\n'
                '🏃 Умеренная - 1-2 тренировки в неделю и прогулки\n'
                '🏋️ Высокая - 3 тренировки в неделю'
            )
            await update.message.reply_text(message, reply_markup=reply_markup)
            
        except ValueError as e:
            error_message = f'⚠️ {str(e)}\n\n'
            error_message += 'Пожалуйста, введите значения в формате:\nтекущий_вес желаемый_вес\nНапример: 80 75'
            await update.message.reply_text(error_message)
        except Exception as e:
            self.logger.error(f"Error processing weight input for user {user.id}: {str(e)}")
            error_message = '⚠️ К сожалению, произошла ошибка при обработке вашего ввода. Пожалуйста, попробуйте еще раз.'
            await update.message.reply_text(error_message)
            del self.user_states[user.id]

    async def calculate_goals_with_llm(self, current_weight: float, target_weight: float, activity_level: str) -> tuple[dict, str]:
        """Calculate nutrition goals using LLM based on weight and activity level."""
        # Шаг 1: Получаем расчет от LLM
        calculation_prompt = (
            f"Рассчитай оптимальные значения калорий и макронутриентов для человека со следующими параметрами:\n"
            f"- Текущий вес: {current_weight} кг\n"
            f"- Целевой вес: {target_weight} кг\n"
            f"- Уровень активности: {activity_level}\n\n"
            f"Учитывай, что:\n"
            f"- Для набора массы нужен профицит калорий\n"
            f"- Для похудения нужен дефицит калорий\n"
            f"- Для поддержания веса калории должны быть на уровне расхода\n"
            f"- Белка должно быть 1.6-2.2г на кг целевого веса\n"
            f"- Жиров должно быть 20-30% от общего количества калорий\n"
            f"- Остальные калории должны приходиться на углеводы\n\n"
            f"Напиши подробное объяснение расчета, включая:\n"
            f"1. Как рассчитан базовый обмен веществ (BMR) - формула и значения\n"
            f"2. Как учтен уровень активности - коэффициент и почему\n"
            f"3. Как рассчитан профицит/дефицит калорий - сколько и почему\n"
            f"4. Как распределены макронутриенты - расчет для каждого\n"
            f"Объяснение должно быть понятным для обычного человека."
        )
        
        try:
            # Получаем расчет и объяснение
            response = await self.food_analyzer.get_llm_response(calculation_prompt)
            self.logger.info(f"LLM calculation response: {response}")
            
            # Шаг 2: Преобразуем ответ в JSON
            format_prompt = (
                f"Преобразуй следующий текст в JSON формат. ВАЖНО:\n"
                f"1. Верни ТОЛЬКО чистый JSON без каких-либо дополнительных символов или форматирования\n"
                f"2. Не используй markdown, блоки кода или другие форматирования\n"
                f"3. Убедись, что все значения являются числами (не null)\n"
                f"4. Объяснение должно быть разбито на 4 части, каждая часть должна содержать текст:\n"
                f"   - bmr_explanation: как рассчитан базовый обмен (формула и значения)\n"
                f"   - activity_explanation: как учтена активность (коэффициент и почему)\n"
                f"   - calorie_explanation: как рассчитаны калории (сколько и почему)\n"
                f"   - macro_explanation: как распределены макронутриенты (расчет для каждого)\n"
                f"5. Структура должна быть точно такой:\n"
                f"{{\n"
                f'  "goals": {{\n'
                f'    "calories": число,\n'
                f'    "protein": число,\n'
                f'    "fat": число,\n'
                f'    "carbs": число\n'
                f'  }},\n'
                f'  "explanation": {{\n'
                f'    "bmr_explanation": "текст",\n'
                f'    "activity_explanation": "текст",\n'
                f'    "calorie_explanation": "текст",\n'
                f'    "macro_explanation": "текст"\n'
                f'  }}\n'
                f"}}\n\n"
                f"Текст для преобразования:\n{response}"
            )
            
            json_response = await self.food_analyzer.get_llm_response(format_prompt)
            self.logger.info(f"LLM JSON response: {json_response}")
            
            # Очищаем ответ от возможных markdown блоков и лишних символов
            json_response = json_response.strip()
            if json_response.startswith('```'):
                json_response = json_response.split('```')[1]
                if json_response.startswith('json'):
                    json_response = json_response[4:]
            json_response = json_response.strip()
            
            # Удаляем переносы строк и лишние пробелы
            json_response = ' '.join(json_response.split())
            
            # Проверяем и парсим JSON
            if not json_response.startswith('{') or not json_response.endswith('}'):
                self.logger.error(f"Invalid JSON format. Response: {json_response}")
                raise ValueError("Invalid JSON format in LLM response")
            
            try:
                result = json.loads(json_response)
            except json.JSONDecodeError as e:
                self.logger.error(f"JSON decode error: {str(e)}. Response: {json_response}")
                raise ValueError("Invalid JSON format in LLM response")
            
            # Проверяем наличие необходимых полей
            if 'goals' not in result or 'explanation' not in result:
                self.logger.error(f"Missing required fields. Response: {result}")
                raise ValueError("Missing required fields in LLM response")
            
            # Проверяем структуру goals
            goals = result['goals']
            required_fields = ['calories', 'protein', 'fat', 'carbs']
            if not all(field in goals for field in required_fields):
                self.logger.error(f"Missing required fields in goals. Goals: {goals}")
                raise ValueError("Missing required fields in goals object")
            
            # Проверяем типы значений
            if not all(isinstance(goals[field], (int, float)) for field in required_fields):
                self.logger.error(f"Invalid value types in goals. Goals: {goals}")
                raise ValueError("Invalid value types in goals object")
            
            # Проверяем структуру explanation
            explanation = result['explanation']
            required_explanation_fields = ['bmr_explanation', 'activity_explanation', 'calorie_explanation', 'macro_explanation']
            if not all(field in explanation for field in required_explanation_fields):
                self.logger.error(f"Missing required fields in explanation. Explanation: {explanation}")
                raise ValueError("Missing required fields in explanation object")
            
            # Проверяем, что все поля объяснения содержат текст
            if not all(explanation[field].strip() for field in required_explanation_fields):
                self.logger.error(f"Empty explanation fields. Explanation: {explanation}")
                raise ValueError("Empty explanation fields")
            
            # Округляем значения до целых чисел
            goals = {k: int(round(v)) for k, v in goals.items()}
            
            return goals, explanation
            
        except Exception as e:
            self.logger.error(f"Error calculating goals with LLM: {str(e)}")
            # Fallback to default calculation if LLM fails
            goals = self.calculate_nutrition_goals(current_weight, target_weight, activity_level)
            return goals, {
                "bmr_explanation": "Базовый обмен веществ рассчитан по формуле Миффлина-Сан Жеора с учетом вашего веса",
                "activity_explanation": f"Уровень активности '{activity_level}' учтен с коэффициентом для расчета общего расхода калорий",
                "calorie_explanation": f"Калории рассчитаны с учетом вашей цели {'набора' if target_weight > current_weight else 'похудения' if target_weight < current_weight else 'поддержания'} веса",
                "macro_explanation": f"Белок: {goals['protein']}г (2г/кг), жиры: {goals['fat']}г (25% калорий), углеводы: {goals['carbs']}г (остаток калорий)"
            }

    async def handle_activity_level_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle activity level selection."""
        query = update.callback_query
        user = update.effective_user
        
        try:
            activity_level = query.data.replace('activity_', '')
            current_weight = context.user_data['current_weight']
            target_weight = context.user_data['target_weight']
            
            # Show loading message and typing action
            await context.bot.send_chat_action(chat_id=user.id, action=ChatAction.TYPING)
            await query.message.edit_text("🤔 Рассчитываю оптимальные значения калорий и макронутриентов...")
            
            # Calculate goals using LLM
            goals, explanation = await self.calculate_goals_with_llm(current_weight, target_weight, activity_level)
            
            # Save the goals
            self.db.set_user_goals(user.id, goals)
            self.logger.info(f"Set weight-based goals for user {user.id}: {goals}")
            
            # Clear the state
            del self.user_states[user.id]
            del context.user_data['current_weight']
            del context.user_data['target_weight']
            
            response = (
                f'✅ Цели установлены!\n\n'
                f'📊 Ваши цели по питанию:\n'
                f'• Калории: {goals["calories"]}\n'
                f'• Белки: {goals["protein"]}г\n'
                f'• Жиры: {goals["fat"]}г\n'
                f'• Углеводы: {goals["carbs"]}г\n\n'
                f'📝 Как это рассчитано:\n\n'
                f'1️⃣ Базовый обмен веществ:\n{explanation["bmr_explanation"]}\n\n'
                f'2️⃣ Учет активности:\n{explanation["activity_explanation"]}\n\n'
                f'3️⃣ Расчет калорий:\n{explanation["calorie_explanation"]}\n\n'
                f'4️⃣ Распределение макронутриентов:\n{explanation["macro_explanation"]}\n\n'
                f'💡 Вы можете вводить информацию о приемах пищи прямо в чат!\n'
                f'Просто напишите, что вы съели, например: "тарелка овсянки с бананом и орехами"'
            )
            
            await query.message.edit_text(response)
            self.logger.info(f"Sent goal confirmation to user {user.id}")
            
        except Exception as e:
            self.logger.error(f"Error setting weight-based goals for user {user.id}: {str(e)}")
            error_message = '⚠️ К сожалению, произошла ошибка при установке целей. Пожалуйста, попробуйте еще раз.'
            await query.message.edit_text(error_message)
            del self.user_states[user.id]

    async def show_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show the main menu with all available options."""
        user = update.effective_user
        self.logger.info(f"Showing main menu for user {user.id}")
        
        # Get current progress
        try:
            progress_data = self.db.get_user_progress(user.id)
            self.logger.info(f"Retrieved progress data for user {user.id}: {progress_data}")
            
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
            self.logger.error(f"Error retrieving progress for user {user.id}: {str(e)}")
            progress_text = '⚠️ Не удалось получить информацию о вашем прогрессе.\n\n'
        
        message = (
            f'👋 Привет, {user.first_name}! Я помогу вам отслеживать ваше питание.\n\n'
            f'{progress_text}'
            '💡 Вы можете вводить информацию о приемах пищи прямо в чат!\n'
            'Просто напишите, что вы съели, например: "тарелка овсянки с бананом и орехами"'
        )
        
        await update.message.reply_text(message)

    async def handle_meal_description(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle meal description input."""
        user = update.effective_user
        description = update.message.text
        self.logger.info(f"User {user.id} submitted meal description: {description}")
        
        try:
            # Check if user has goals set
            progress_data = self.db.get_user_progress(user.id)
            if not progress_data:
                message = (
                    '📝 Пожалуйста, сначала установите цели по питанию, чтобы я мог помочь вам отслеживать ваше питание.\n\n'
                    'Используйте команду /set_goals для установки целей.'
                )
                await update.message.reply_text(message)
                return 

            # Show typing action while analyzing
            await context.bot.send_chat_action(chat_id=user.id, action=ChatAction.TYPING)
            
            # Analyze the meal using OpenAI
            self.logger.info(f"Starting meal analysis for user {user.id}")
            analysis = await self.food_analyzer.analyze_meal(description)
            self.logger.info(f"Meal analysis completed for user {user.id}: {analysis}")
            
            # Save to database
            self.logger.info(f"Saving meal to database for user {user.id}")
            self.db.save_meal(user.id, description, analysis)
            
            # Update metrics
            self.metrics['meal_counter'].inc()
            self.metrics['user_counter'].inc()
            
            # Calculate remaining values
            remaining = {
                'calories': progress_data['goal_calories'] - progress_data['calories'],
                'protein': progress_data['goal_protein'] - progress_data['protein'],
                'fat': progress_data['goal_fat'] - progress_data['fat'],
                'carbs': progress_data['goal_carbs'] - progress_data['carbs']
            }
            self.logger.info(f"Calculated remaining targets for user {user.id}: {remaining}")
            
            # Get feedback from LLM
            feedback_prompt = (
                f"Пользователь только что залогировал прием пищи: {description}\n"
                f"Питательная ценность: {analysis}\n"
                f"Текущие дневные итоги: {progress_data}\n"
                f"Оставшиеся дневные цели: {remaining}\n\n"
                "Дайте краткий, дружелюбный отзыв об этом приеме пищи в контексте дневных целей. "
                "Включите простое сравнение питательных веществ приема пищи с оставшимися дневными целями. "
                "Будьте краткими и ободряющими."
            )
            
            # Show typing action while generating feedback
            await context.bot.send_chat_action(chat_id=user.id, action=ChatAction.TYPING)
            
            self.logger.info(f"Requesting feedback from LLM for user {user.id}")
            feedback = await self.food_analyzer.get_feedback(feedback_prompt)
            self.logger.info(f"Received feedback from LLM for user {user.id}: {feedback}")
            
            # Prepare response
            response = (
                f'✅ Прием пищи сохранен!\n\n'
                f'📊 Этот прием пищи:\n'
                f'• Калории: {analysis["calories"]}\n'
                f'• Белки: {analysis["protein"]}г\n'
                f'• Жиры: {analysis["fat"]}г\n'
                f'• Углеводы: {analysis["carbs"]}г\n\n'
                f'🎯 Осталось на сегодня:\n'
                f'• Калории: {remaining["calories"]}\n'
                f'• Белки: {remaining["protein"]}г\n'
                f'• Жиры: {remaining["fat"]}г\n'
                f'• Углеводы: {remaining["carbs"]}г\n\n'
                f'💬 Отзыв:\n{feedback}'
            )
            
            await update.message.reply_text(response)
            self.logger.info(f"Response sent to user {user.id}")
            
        except Exception as e:
            self.logger.error(f"Error processing meal for user {user.id}: {str(e)}")
            error_message = '⚠️ К сожалению, произошла ошибка при обработке вашего приема пищи. Пожалуйста, попробуйте еще раз.'
            await update.message.reply_text(error_message)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a message when the command /start is issued."""
        user = update.effective_user
        self.logger.info(f"User {user.id} ({user.first_name}) started the bot")
        
        # Get current progress
        try:
            progress_data = self.db.get_user_progress(user.id)
            self.logger.info(f"Retrieved progress data for user {user.id}: {progress_data}")
            
            if progress_data:
                progress_text = (
                    f'\n📊 Ваш текущий прогресс:\n'
                    f'• Калории: {progress_data["calories"]}/{progress_data["goal_calories"]}\n'
                    f'• Белки: {progress_data["protein"]}/{progress_data["goal_protein"]}г\n'
                    f'• Жиры: {progress_data["fat"]}/{progress_data["goal_fat"]}г\n'
                    f'• Углеводы: {progress_data["carbs"]}/{progress_data["goal_carbs"]}г\n\n'
                    '💡 Вы можете вводить информацию о приемах пищи прямо в чат!\n'
                    'Просто напишите, что вы съели, например: "тарелка овсянки с бананом и орехами"'
                )
                message = (
                    f'👋 Привет, {user.first_name}! Я помогу вам отслеживать ваше питание.\n\n'
                    f'{progress_text}'
                )
                await update.message.reply_text(message)
            else:
                keyboard = [
                    [
                        InlineKeyboardButton("📉 Похудение", callback_data='goal_weight_loss'),
                        InlineKeyboardButton("📈 Набор массы", callback_data='goal_muscle_gain'),
                    ],
                    [
                        InlineKeyboardButton("⚖️ Поддержание", callback_data='goal_maintenance'),
                        InlineKeyboardButton("✏️ Свои цели", callback_data='goal_custom'),
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                message = (
                    f'👋 Привет, {user.first_name}! Я помогу вам отслеживать ваше питание.\n\n'
                    '📝 Вы еще не установили цели по питанию.\n\n'
                    'Выберите вашу цель:'
                )
                await update.message.reply_text(message, reply_markup=reply_markup)
        except Exception as e:
            self.logger.error(f"Error retrieving progress for user {user.id}: {str(e)}")
            keyboard = [
                [
                    InlineKeyboardButton("📉 Похудение", callback_data='goal_weight_loss'),
                    InlineKeyboardButton("📈 Набор массы", callback_data='goal_muscle_gain'),
                ],
                [
                    InlineKeyboardButton("⚖️ Поддержание", callback_data='goal_maintenance'),
                    InlineKeyboardButton("✏️ Свои цели", callback_data='goal_custom'),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            message = (
                f'👋 Привет, {user.first_name}! Я помогу вам отслеживать ваше питание.\n\n'
                '📝 Вы еще не установили цели по питанию.\n\n'
                'Выберите вашу цель:'
            )
            await update.message.reply_text(message, reply_markup=reply_markup)

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a message when the command /help is issued."""
        user = update.effective_user
        self.logger.info(f"User {user.id} requested help")
        
        # Get current progress
        try:
            progress_data = self.db.get_user_progress(user.id)
            self.logger.info(f"Retrieved progress data for user {user.id}: {progress_data}")
            
            if progress_data:
                progress_text = (
                    f'\n📊 Ваш текущий прогресс:\n'
                    f'• Калории: {progress_data["calories"]}/{progress_data["goal_calories"]}\n'
                    f'• Белки: {progress_data["protein"]}/{progress_data["goal_protein"]}г\n'
                    f'• Жиры: {progress_data["fat"]}/{progress_data["goal_fat"]}г\n'
                    f'• Углеводы: {progress_data["carbs"]}/{progress_data["goal_carbs"]}г\n'
                )
                message = (
                    '🤖 Я помогу вам отслеживать ваше питание!\n\n'
                    '💡 Вы можете вводить информацию о приемах пищи прямо в чат!\n'
                    'Просто напишите, что вы съели, например: "тарелка овсянки с бананом и орехами"\n\n'
                    '📋 Доступные команды:\n'
                    '/today - Показать лог дня\n'
                    '/weekly - Показать статистику\n'
                    '/recommendations - Получить рекомендации\n'
                    '/set_goals - Установить цели по питанию\n'
                    '/help - Показать справку\n\n'
                    f'{progress_text}'
                )
                await update.message.reply_text(message)
            else:
                keyboard = [
                    [
                        InlineKeyboardButton("📉 Похудение", callback_data='goal_weight_loss'),
                        InlineKeyboardButton("📈 Набор массы", callback_data='goal_muscle_gain'),
                    ],
                    [
                        InlineKeyboardButton("⚖️ Поддержание", callback_data='goal_maintenance'),
                        InlineKeyboardButton("✏️ Свои цели", callback_data='goal_custom'),
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                message = (
                    '🤖 Я помогу вам отслеживать ваше питание!\n\n'
                    '📝 Вы еще не установили цели по питанию.\n\n'
                    'Выберите вашу цель:'
                )
                await update.message.reply_text(message, reply_markup=reply_markup)
        except Exception as e:
            self.logger.error(f"Error retrieving progress for user {user.id}: {str(e)}")
            keyboard = [
                [
                    InlineKeyboardButton("📉 Похудение", callback_data='goal_weight_loss'),
                    InlineKeyboardButton("📈 Набор массы", callback_data='goal_muscle_gain'),
                ],
                [
                    InlineKeyboardButton("⚖️ Поддержание", callback_data='goal_maintenance'),
                    InlineKeyboardButton("✏️ Свои цели", callback_data='goal_custom'),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            message = (
                '🤖 Я помогу вам отслеживать ваше питание!\n\n'
                '📝 Вы еще не установили цели по питанию.\n\n'
                'Выберите вашу цель:'
            )
            await update.message.reply_text(message, reply_markup=reply_markup)

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks."""
        query = update.callback_query
        user = update.effective_user
        
        await query.answer()
        
        if query.data == 'main_menu':
            await self.show_main_menu(update, context)
        elif query.data == 'set_goals':
            await self.set_goals(update, context)
        elif query.data == 'today':
            await self.today(update, context)
        elif query.data == 'weekly':
            await self.weekly(update, context)
        elif query.data == 'recommendations':
            await self.recommendations(update, context)
        elif query.data.startswith('goal_'):
            goal_type = query.data[5:]  # Remove 'goal_' prefix
            await self.handle_goal_selection(update, context, goal_type)
        elif query.data == 'weight_based':
            # Set state to waiting for weight information
            self.user_states[user.id] = 'waiting_for_weight_info'
            
            message = (
                'Введите ваш текущий вес и желаемый вес через пробел.\n'
                'Например: 70 75\n\n'
                'Это означает, что ваш текущий вес 70 кг, и вы хотите достичь веса 75 кг.'
            )
            await query.message.edit_text(message)
        elif query.data.startswith('activity_'):
            await self.handle_activity_level_input(update, context)

    async def handle_goal_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE, goal_type: str):
        """Handle goal selection."""
        user = update.effective_user
        self.logger.info(f"User {user.id} selected goal type: {goal_type}")
        
        if goal_type == 'custom':
            # Set state to waiting for custom goals input
            self.user_states[user.id] = 'waiting_for_custom_goals'
            
            message = (
                'Введите ваши цели в формате:\n'
                'калории белки жиры углеводы\n\n'
                'Например: 2000 150 60 200'
            )
            await update.callback_query.message.edit_text(message)
            return
        
        if goal_type == 'weight_based':
            # Set state to waiting for weight information
            self.user_states[user.id] = 'waiting_for_weight_info'
            
            keyboard = [
                [
                    InlineKeyboardButton("📉 Похудение", callback_data='weight_loss'),
                    InlineKeyboardButton("📈 Набор массы", callback_data='weight_gain'),
                ],
                [
                    InlineKeyboardButton("⚖️ Поддержание", callback_data='weight_maintain'),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            message = (
                'Выберите вашу цель по весу:'
            )
            await update.callback_query.message.edit_text(message, reply_markup=reply_markup)
            return
        
        try:
            # Set predefined goals
            goals = self.goals_manager.get_predefined_goals(goal_type)
            self.db.set_user_goals(user.id, goals)
            self.logger.info(f"Set goals for user {user.id}: {goals}")
            
            response = (
                f'✅ Цели установлены!\n\n'
                f'📊 Ваши цели по питанию:\n'
                f'• Калории: {goals["calories"]}\n'
                f'• Белки: {goals["protein"]}г\n'
                f'• Жиры: {goals["fat"]}г\n'
                f'• Углеводы: {goals["carbs"]}г\n\n'
                '💡 Вы можете вводить информацию о приемах пищи прямо в чат!\n'
                'Просто напишите, что вы съели, например: "тарелка овсянки с бананом и орехами"'
            )
            
            await update.callback_query.message.edit_text(response)
            self.logger.info(f"Sent goal confirmation to user {user.id}")
            
        except Exception as e:
            self.logger.error(f"Error setting goals for user {user.id}: {str(e)}")
            error_message = '⚠️ К сожалению, произошла ошибка при установке целей. Пожалуйста, попробуйте еще раз.'
            await update.callback_query.message.edit_text(error_message)

    async def set_goals(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /set_goals command."""
        user = update.effective_user
        self.logger.info(f"User {user.id} requested to set goals")
        
        keyboard = [
            [
                InlineKeyboardButton("📊 На основе веса", callback_data='weight_based'),
                InlineKeyboardButton("✏️ Свои цели", callback_data='goal_custom'),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = 'Выберите способ установки целей:'
        await update.message.reply_text(message, reply_markup=reply_markup)

    async def today(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /today command."""
        user = update.effective_user
        self.logger.info(f"User {user.id} requested today's meals")
        
        try:
            meals = self.db.get_today_meals(user.id)
            self.logger.info(f"Retrieved {len(meals)} meals for user {user.id}")
            
            if not meals:
                message = '📝 Вы еще не добавили приемы пищи сегодня.'
                await update.message.reply_text(message)
                return
            
            # Get current progress for totals
            progress_data = self.db.get_user_progress(user.id)
            
            response = '🍽 Лог дня:\n\n'
            
            # Add each meal with clear formatting
            for i, meal in enumerate(meals, 1):
                response += f'🍴 Прием пищи #{i}\n'
                response += f'📝 {meal[0]}\n'
                response += f'📊 Питательная ценность:\n'
                response += f'   • Калории: {meal[1]}\n'
                response += f'   • Белки: {meal[2]}г\n'
                response += f'   • Жиры: {meal[3]}г\n'
                response += f'   • Углеводы: {meal[4]}г\n\n'
            
            # Add daily totals if goals are set
            if progress_data:
                response += '📈 Дневные итоги:\n'
                response += f'• Калории: {progress_data["calories"]}/{progress_data["goal_calories"]}\n'
                response += f'• Белки: {progress_data["protein"]}/{progress_data["goal_protein"]}г\n'
                response += f'• Жиры: {progress_data["fat"]}/{progress_data["goal_fat"]}г\n'
                response += f'• Углеводы: {progress_data["carbs"]}/{progress_data["goal_carbs"]}г\n\n'
                
                # Calculate and show remaining values
                remaining = {
                    'calories': progress_data['goal_calories'] - progress_data['calories'],
                    'protein': progress_data['goal_protein'] - progress_data['protein'],
                    'fat': progress_data['goal_fat'] - progress_data['fat'],
                    'carbs': progress_data['goal_carbs'] - progress_data['carbs']
                }
                
                response += '🎯 Осталось на сегодня:\n'
                response += f'• Калории: {remaining["calories"]}\n'
                response += f'• Белки: {remaining["protein"]}г\n'
                response += f'• Жиры: {remaining["fat"]}г\n'
                response += f'• Углеводы: {remaining["carbs"]}г'
            
            await update.message.reply_text(response)
            self.logger.info(f"Today's meals sent to user {user.id}")
            
        except Exception as e:
            self.logger.error(f"Error retrieving today's meals for user {user.id}: {str(e)}")
            error_message = '⚠️ К сожалению, произошла ошибка при получении ваших приемов пищи. Пожалуйста, попробуйте еще раз.'
            await update.message.reply_text(error_message)

    async def weekly(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /weekly command."""
        user = update.effective_user
        self.logger.info(f"User {user.id} requested weekly summary")
        
        try:
            weekly_data = self.db.get_weekly_summary(user.id)
            self.logger.info(f"Retrieved weekly data for user {user.id}: {weekly_data}")
            
            if not weekly_data:
                message = '📝 Вы не залогировали приемы пищи за последние 7 дней.'
                await update.message.reply_text(message)
                return
            
            response = '📊 Ваше потребление за последние 7 дней:\n\n'
            
            # Get goals from the first day's data
            goal_calories = weekly_data[0]['goal_calories']
            goal_protein = weekly_data[0]['goal_protein']
            goal_fat = weekly_data[0]['goal_fat']
            goal_carbs = weekly_data[0]['goal_carbs']
            
            # Initialize totals for averages
            total_days = len(weekly_data)
            total_calories = 0
            total_protein = 0
            total_fat = 0
            total_carbs = 0
            days_reached_calories = 0
            days_reached_protein = 0
            days_reached_fat = 0
            days_reached_carbs = 0
            
            for day in weekly_data:
                date_str = day['date'].strftime('%Y-%m-%d')
                response += f'📅 {date_str}:\n'
                response += f'• Калории: {day["calories"]}/{goal_calories}'
                response += ' ✅' if day['reached_goals']['calories'] else ' ❌'
                response += f'\n• Белки: {day["protein"]:.1f}/{goal_protein}г'
                response += ' ✅' if day['reached_goals']['protein'] else ' ❌'
                response += f'\n• Жиры: {day["fat"]:.1f}/{goal_fat}г'
                response += ' ✅' if day['reached_goals']['fat'] else ' ❌'
                response += f'\n• Углеводы: {day["carbs"]:.1f}/{goal_carbs}г'
                response += ' ✅' if day['reached_goals']['carbs'] else ' ❌'
                response += '\n\n'
                
                # Update totals
                total_calories += day['calories']
                total_protein += day['protein']
                total_fat += day['fat']
                total_carbs += day['carbs']
                
                # Update goal achievement counters
                if day['reached_goals']['calories']:
                    days_reached_calories += 1
                if day['reached_goals']['protein']:
                    days_reached_protein += 1
                if day['reached_goals']['fat']:
                    days_reached_fat += 1
                if day['reached_goals']['carbs']:
                    days_reached_carbs += 1
            
            # Calculate averages
            avg_calories = total_calories / total_days
            avg_protein = total_protein / total_days
            avg_fat = total_fat / total_days
            avg_carbs = total_carbs / total_days
            
            response += f'📈 Средние показатели за неделю:\n'
            response += f'• Калории: {avg_calories:.0f}/{goal_calories}\n'
            response += f'• Белки: {avg_protein:.1f}/{goal_protein}г\n'
            response += f'• Жиры: {avg_fat:.1f}/{goal_fat}г\n'
            response += f'• Углеводы: {avg_carbs:.1f}/{goal_carbs}г\n\n'
            
            response += f'🎯 Достижение целей:\n'
            response += f'• Калории: {days_reached_calories}/{total_days} дней ({days_reached_calories/total_days*100:.0f}%)\n'
            response += f'• Белки: {days_reached_protein}/{total_days} дней ({days_reached_protein/total_days*100:.0f}%)\n'
            response += f'• Жиры: {days_reached_fat}/{total_days} дней ({days_reached_fat/total_days*100:.0f}%)\n'
            response += f'• Углеводы: {days_reached_carbs}/{total_days} дней ({days_reached_carbs/total_days*100:.0f}%)'
            
            await update.message.reply_text(response)
            self.logger.info(f"Weekly summary sent to user {user.id}")
            
        except Exception as e:
            self.logger.error(f"Error retrieving weekly summary for user {user.id}: {str(e)}")
            error_message = '⚠️ К сожалению, произошла ошибка при получении вашей недельной статистики. Пожалуйста, попробуйте еще раз.'
            await update.message.reply_text(error_message)

    async def recommendations(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /recommendations command."""
        user = update.effective_user
        self.logger.info(f"User {user.id} requested recommendations")
        
        try:
            # Get current progress
            progress_data = self.db.get_user_progress(user.id)
            if not progress_data:
                message = '📝 Пожалуйста, сначала установите цели по питанию, чтобы получить персонализированные рекомендации.'
                self.logger.info(f"No goals set for user {user.id}, cannot generate recommendations")
                await update.message.reply_text(message)
                return
            
            # Calculate remaining values
            remaining = {
                'calories': progress_data['goal_calories'] - progress_data['calories'],
                'protein': progress_data['goal_protein'] - progress_data['protein'],
                'fat': progress_data['goal_fat'] - progress_data['fat'],
                'carbs': progress_data['goal_carbs'] - progress_data['carbs']
            }
            self.logger.info(f"Calculated remaining targets for user {user.id}: {remaining}")
            
            # Show typing action while generating recommendations
            await context.bot.send_chat_action(chat_id=user.id, action=ChatAction.TYPING)
            
            # Get recommendations from LLM
            self.logger.info(f"Requesting recommendations from LLM for user {user.id}")
            recommendations = await self.food_analyzer.get_recommendations(progress_data, remaining)
            self.logger.info(f"Received recommendations from LLM for user {user.id}: {recommendations}")
            
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
            
            await update.message.reply_text(response)
            self.logger.info(f"Recommendations sent to user {user.id}")
            
        except Exception as e:
            self.logger.error(f"Error generating recommendations for user {user.id}: {str(e)}")
            error_message = '⚠️ К сожалению, произошла ошибка при генерации рекомендаций. Пожалуйста, попробуйте еще раз.'
            await update.message.reply_text(error_message)

    def calculate_nutrition_goals(self, current_weight: float, target_weight: float, activity_level: str = 'moderate') -> dict:
        """Calculate nutrition goals based on current and target weight."""
        # Calculate base metabolic rate (BMR) using Mifflin-St Jeor Equation
        # For simplicity, we'll use a fixed age (30) and height (170cm)
        bmr = 10 * current_weight + 6.25 * 170 - 5 * 30 + 5
        
        # Activity level multipliers
        activity_multipliers = {
            'sedentary': 1.2,      # Little or no exercise
            'light': 1.375,        # Light exercise 1-3 days/week
            'moderate': 1.55,      # Moderate exercise 3-5 days/week
            'active': 1.725,       # Hard exercise 6-7 days/week
            'very_active': 1.9     # Very hard exercise & physical job
        }
        
        # Calculate total daily energy expenditure (TDEE)
        tdee = bmr * activity_multipliers[activity_level]
        
        # Adjust calories based on weight goal
        weight_difference = target_weight - current_weight
        if weight_difference < 0:  # Weight loss
            daily_calories = tdee - 500  # 500 calorie deficit for weight loss
        elif weight_difference > 0:  # Weight gain
            daily_calories = tdee + 500  # 500 calorie surplus for weight gain
        else:  # Maintenance
            daily_calories = tdee
        
        # Calculate macronutrient distribution
        # Protein: 2g per kg of target weight
        protein = target_weight * 2
        
        # Fat: 25% of total calories
        fat = (daily_calories * 0.25) / 9  # 9 calories per gram of fat
        
        # Carbs: remaining calories
        remaining_calories = daily_calories - (protein * 4 + fat * 9)
        carbs = remaining_calories / 4  # 4 calories per gram of carbs
        
        return {
            'calories': round(daily_calories),
            'protein': round(protein),
            'fat': round(fat),
            'carbs': round(carbs)
        }

def main():
    """Start the bot."""
    logger.info("Starting bot...")
    
    # Create the Application and pass it your bot's token
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    bot = FoodTrackerBot()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("menu", bot.show_main_menu))
    application.add_handler(CommandHandler("help", bot.help))
    application.add_handler(CommandHandler("set_goals", bot.set_goals))
    application.add_handler(CommandHandler("today", bot.today))
    application.add_handler(CommandHandler("weekly", bot.weekly))
    application.add_handler(CommandHandler("recommendations", bot.recommendations))
    
    # Add message handler for meal descriptions
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))
    
    # Add callback query handler for buttons
    application.add_handler(CallbackQueryHandler(bot.button_callback))
    
    # Initialize bot commands
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(bot.initialize())
        # Start the Bot
        logger.info("Bot is running and polling for updates...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    finally:
        loop.close()

if __name__ == '__main__':
    main() 