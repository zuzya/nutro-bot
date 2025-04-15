import os
from openai import AsyncOpenAI
from dotenv import load_dotenv
import logging

load_dotenv()

logger = logging.getLogger(__name__)

class FoodAnalyzer:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.system_prompt = """You are a nutrition expert. Your task is to analyze food descriptions and provide accurate nutritional information.
        For each meal description, provide:
        1. Total calories
        2. Protein in grams
        3. Fat in grams
        4. Carbohydrates in grams
        
        Be as accurate as possible in your estimates. Consider typical portion sizes and common ingredients.
        Return the response in JSON format with the following structure:
        {
            "calories": number,
            "protein": number,
            "fat": number,
            "carbs": number
        }
        """

    async def analyze_meal(self, description: str) -> dict:
        """Analyze a meal description and return nutritional information."""
        try:
            logger.info(f"Analyzing meal description: {description}")
            
            response = await self.client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": f"Analyze this meal: {description}"}
                ],
                response_format={"type": "json_object"}
            )
            
            # Extract and parse the JSON response
            result = response.choices[0].message.content
            logger.info(f"LLM analysis response: {result}")
            
            return eval(result)  # Safe in this context as we control the output format
            
        except Exception as e:
            logger.error(f"Error analyzing meal: {str(e)}")
            # Return default values in case of error
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
            
            response = await self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a helpful nutrition assistant. Provide brief, friendly feedback about meals in the context of daily goals. Be encouraging and practical."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=150
            )
            
            feedback = response.choices[0].message.content.strip()
            logger.info(f"LLM feedback response: {feedback}")
            return feedback
            
        except Exception as e:
            logger.error(f"Error generating feedback: {str(e)}")
            return "I couldn't generate specific feedback at the moment, but your meal has been logged successfully!"

    async def get_recommendations(self, progress_data: dict, remaining: dict) -> str:
        """Generate personalized nutrition recommendations using the LLM."""
        try:
            prompt = (
                f"User's current daily nutrition:\n"
                f"Calories: {progress_data['calories']}/{progress_data['goal_calories']}\n"
                f"Protein: {progress_data['protein']}/{progress_data['goal_protein']}g\n"
                f"Fat: {progress_data['fat']}/{progress_data['goal_fat']}g\n"
                f"Carbs: {progress_data['carbs']}/{progress_data['goal_carbs']}g\n\n"
                f"Remaining for today:\n"
                f"Calories: {remaining['calories']}\n"
                f"Protein: {remaining['protein']}g\n"
                f"Fat: {remaining['fat']}g\n"
                f"Carbs: {remaining['carbs']}g\n\n"
                "Provide 2-3 specific, actionable recommendations for the user's next meal or snacks "
                "based on their remaining daily targets. Focus on practical suggestions that would help "
                "them meet their goals. Keep it concise and friendly."
            )
            
            logger.info(f"Generating recommendations with prompt: {prompt}")
            
            response = await self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a helpful nutrition assistant. Provide specific, actionable recommendations based on the user's current nutrition status and remaining daily targets."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=200
            )
            
            recommendations = response.choices[0].message.content.strip()
            logger.info(f"LLM recommendations response: {recommendations}")
            return recommendations
            
        except Exception as e:
            logger.error(f"Error generating recommendations: {str(e)}")
            return "I couldn't generate specific recommendations at the moment. Please try again later!" 