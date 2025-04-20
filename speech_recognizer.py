import os
import json
import logging
import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class SpeechRecognizer:
    def __init__(self):
        self.folder_id = os.getenv('YANDEX_FOLDER_ID')
        self.iam_token = os.getenv('YANDEX_IAM_TOKEN')
        self.api_url = 'https://stt.api.cloud.yandex.net/speech/v1/stt:recognize'
        
        if not self.folder_id or not self.iam_token:
            raise ValueError("YANDEX_FOLDER_ID and YANDEX_IAM_TOKEN must be set in environment variables")

    async def recognize_audio(self, audio_data: bytes) -> str:
        """
        Recognize speech from audio data using Yandex SpeechKit.
        
        Args:
            audio_data (bytes): Raw audio data in OGG format
            
        Returns:
            str: Recognized text or empty string if recognition failed
        """
        try:
            headers = {
                'Authorization': f'Bearer {self.iam_token}',
                'Content-Type': 'audio/ogg'
            }
            
            params = {
                'folderId': self.folder_id,
                'lang': 'ru-RU',
                'format': 'oggopus',
                'sampleRateHertz': 48000
            }
            
            response = requests.post(
                self.api_url,
                headers=headers,
                params=params,
                data=audio_data
            )
            
            if response.status_code == 200:
                result = response.json()
                if 'result' in result:
                    return result['result']
                else:
                    logger.error(f"Recognition failed: {result}")
                    return ""
            else:
                logger.error(f"API request failed with status {response.status_code}: {response.text}")
                return ""
                
        except Exception as e:
            logger.error(f"Error during speech recognition: {str(e)}")
            return ""

    async def is_speech_quality_good(self, audio_data: bytes) -> bool:
        """
        Check if the audio quality is good enough for speech recognition.
        This is a simple implementation that can be enhanced based on specific requirements.
        
        Args:
            audio_data (bytes): Raw audio data
            
        Returns:
            bool: True if audio quality is good, False otherwise
        """
        # Basic check for minimum audio length (e.g., 1 second)
        # You can enhance this with more sophisticated audio quality checks
        return len(audio_data) > 48000  # Assuming 48kHz sample rate, minimum 1 second 