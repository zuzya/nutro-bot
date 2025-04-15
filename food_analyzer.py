import os
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

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
            return eval(result)  # Safe in this context as we control the output format
            
        except Exception as e:
            print(f"Error analyzing meal: {e}")
            # Return default values in case of error
            return {
                "calories": 0,
                "protein": 0,
                "fat": 0,
                "carbs": 0
            } 