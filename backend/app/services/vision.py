import base64
import json
from app.services.groq_client import GroqClient


EXTRACT_PROMPT = """You are the vision layer for Mentis, an AI Live AR Tutor.
The selected learning mode is: __MODE__.

Look at this image and:
1. Identify the type of problem (math, physics, chemistry, coding, biology, etc.)
2. Extract ALL text content visible in the image
3. Identify useful regions for AR teaching such as the question, formula, diagram labels, code block, graph, or table
4. Return ONLY valid JSON in this exact format:
{
  "type": "math",
  "title": "brief problem title",
  "content": "full extracted problem text",
  "difficulty": "easy|medium|hard",
  "detectedElements": ["equation", "graph", "diagram"],
  "arTargets": [
    {
      "label": "main equation",
      "x": 0.18,
      "y": 0.34,
      "width": 0.64,
      "height": 0.18
    }
  ]
}"""


class VisionService:
    def __init__(self, groq: GroqClient):
        self.groq = groq

    def extract_problem(self, image_bytes: bytes, mode: str = 'math') -> dict:
        image_b64 = base64.b64encode(image_bytes).decode('utf-8')
        try:
            result = self.groq.vision(image_b64, EXTRACT_PROMPT.replace('__MODE__', mode))
        except Exception:
            return {
                'type': mode or 'math',
                'title': f'{(mode or "Math").title()} scan',
                'content': 'AI vision is not configured yet. Use this demo problem: 2x + 5 = 15. Solve for x.',
                'difficulty': 'easy',
                'detectedElements': ['equation', 'text'],
                'arTargets': [{'label': 'main equation', 'x': 0.16, 'y': 0.34, 'width': 0.68, 'height': 0.16}],
            }

        try:
            cleaned = result.strip()
            if cleaned.startswith('```json'):
                cleaned = cleaned.split('```json')[1].split('```')[0].strip()
            elif cleaned.startswith('```'):
                cleaned = cleaned.split('```')[1].split('```')[0].strip()
            return json.loads(cleaned)
        except (json.JSONDecodeError, IndexError):
            return {
                'type': mode or 'unknown',
                'title': 'Extracted Problem',
                'content': result,
                'difficulty': 'medium',
                'detectedElements': ['text'],
                'arTargets': [{'label': 'problem area', 'x': 0.12, 'y': 0.28, 'width': 0.76, 'height': 0.22}],
            }

vision_service = VisionService(GroqClient())
