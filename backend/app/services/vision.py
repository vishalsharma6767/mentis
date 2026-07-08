import base64
import json
from app.services.groq_client import GroqClient


EXTRACT_PROMPT = """You are a math and science problem extractor. Look at this image and:
1. Identify the type of problem (math, physics, chemistry, coding, biology, etc.)
2. Extract ALL text content visible in the image
3. Return ONLY valid JSON in this exact format:
{
  "type": "math",
  "title": "brief problem title",
  "content": "full extracted problem text",
  "difficulty": "easy|medium|hard"
}"""


class VisionService:
    def __init__(self, groq: GroqClient):
        self.groq = groq

    def extract_problem(self, image_bytes: bytes) -> dict:
        image_b64 = base64.b64encode(image_bytes).decode('utf-8')
        result = self.groq.vision(image_b64, EXTRACT_PROMPT)

        try:
            cleaned = result.strip()
            if cleaned.startswith('```json'):
                cleaned = cleaned.split('```json')[1].split('```')[0].strip()
            elif cleaned.startswith('```'):
                cleaned = cleaned.split('```')[1].split('```')[0].strip()
            return json.loads(cleaned)
        except (json.JSONDecodeError, IndexError):
            return {
                'type': 'unknown',
                'title': 'Extracted Problem',
                'content': result,
                'difficulty': 'medium',
            }
