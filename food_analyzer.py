import os
import json
import httpx
from dotenv import load_dotenv
import logging

load_dotenv()

logger = logging.getLogger(__name__)

class FoodAnalyzer:
    def __init__(self):
        self.api_key = os.getenv('OPENAI_API_KEY')
        self.proxy_url = os.getenv('OPENAI_PROXY_URL')
        self.system_prompt = """Вы - эксперт по питанию. Ваша задача - анализировать описания еды и предоставлять точную информацию о питательной ценности.
        Для каждого описания еды предоставьте:
        1. Общее количество калорий
        2. Белки в граммах
        3. Жиры в граммах
        4. Углеводы в граммах
        
        Будьте максимально точны в своих оценках. Учитывайте типичные размеры порций и распространенные ингредиенты.
        Возвращайте ответ в формате JSON со следующей структурой:
        {
            "calories": число,
            "protein": число,
            "fat": число,
            "carbs": число
        }
        """

    async def _make_request(self, payload: dict) -> dict:
        """Make a request to OpenAI API with proxy support."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        try:
            with httpx.Client(
                proxies=self.proxy_url,
                timeout=30.0,
                verify=False  # Only disable SSL verification for proxy
            ) as client:
                response = client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=30.0
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"HTTP error occurred: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error making request: {str(e)}")
            raise

    async def analyze_meal(self, description: str) -> dict:
        """Analyze a meal description and return nutritional information."""
        try:
            logger.info(f"Analyzing meal description: {description}")
            
            payload = {
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": f"Analyze this meal: {description}"}
                ],
                "response_format": {"type": "json_object"}
            }
            
            response = await self._make_request(payload)
            result = response['choices'][0]['message']['content']
            logger.info(f"LLM analysis response: {result}")
            
            return json.loads(result)
            
        except Exception as e:
            logger.error(f"Error analyzing meal: {str(e)}")
            return {
                "calories": 0,
                "protein": 0,
                "fat": 0,
                "carbs": 0
            }

    async def get_feedback(self, prompt: str) -> str:
        """Generate feedback about a meal using the LLM."""
        try:
            logger.info(f"Generating feedback with prompt: {prompt}")
            
            payload = {
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "Вы - помощник по питанию. Давайте краткие, дружелюбные отзывы о приемах пищи в контексте дневных целей. Будьте ободряющими и практичными. Отвечайте на русском языке."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 500
            }
            
            response = await self._make_request(payload)
            feedback = response['choices'][0]['message']['content'].strip()
            logger.info(f"LLM feedback response: {feedback}")
            return feedback
            
        except Exception as e:
            logger.error(f"Error generating feedback: {str(e)}")
            return "К сожалению, я не смог сгенерировать конкретный отзыв в данный момент, но ваш прием пищи был успешно сохранен!"

    async def get_recommendations(self, progress_data: dict, remaining: dict) -> str:
        """Generate personalized nutrition recommendations using the LLM."""
        try:
            prompt = (
                f"Текущее дневное питание пользователя:\n"
                f"Калории: {progress_data['calories']}/{progress_data['goal_calories']}\n"
                f"Белки: {progress_data['protein']}/{progress_data['goal_protein']}г\n"
                f"Жиры: {progress_data['fat']}/{progress_data['goal_fat']}г\n"
                f"Углеводы: {progress_data['carbs']}/{progress_data['goal_carbs']}г\n\n"
                f"Осталось на сегодня:\n"
                f"Калории: {remaining['calories']}\n"
                f"Белки: {remaining['protein']}г\n"
                f"Жиры: {remaining['fat']}г\n"
                f"Углеводы: {remaining['carbs']}г\n\n"
                "Предоставьте 2-3 конкретных, практичных рекомендации для следующего приема пищи или перекуса "
                "на основе оставшихся дневных целей. Сосредоточьтесь на практических предложениях, которые помогут "
                "достичь целей. Будьте краткими и дружелюбными. Отвечайте на русском языке."
            )
            
            logger.info(f"Generating recommendations with prompt: {prompt}")
            
            payload = {
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "Вы - помощник по питанию. Предоставляйте конкретные, практичные рекомендации на основе текущего состояния питания пользователя и оставшихся дневных целей. Отвечайте на русском языке."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 500
            }
            
            response = await self._make_request(payload)
            recommendations = response['choices'][0]['message']['content'].strip()
            logger.info(f"LLM recommendations response: {recommendations}")
            return recommendations
            
        except Exception as e:
            logger.error(f"Error generating recommendations: {str(e)}")
            return "К сожалению, я не смог сгенерировать конкретные рекомендации в данный момент. Пожалуйста, попробуйте позже!"

    async def get_llm_response(self, prompt: str) -> str:
        """Get response from LLM for a given prompt."""
        try:
            response = await self._make_request({
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "Ты - эксперт по питанию и фитнесу. Ты помогаешь людям достигать их целей по весу и здоровью."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 1000
            })
            return response['choices'][0]['message']['content']
        except Exception as e:
            logger.error(f"Error getting LLM response: {str(e)}")
            raise 