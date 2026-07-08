import json
from app.services.groq_client import GroqClient


SYSTEM_PROMPT = """You are Mentis, an AI tutor. You teach step by step without giving answers immediately.
- Adapt explanations to the student's level (beginner, intermediate, advanced)
- Break problems into small logical steps
- Ask guiding questions before revealing answers
- Praise progress and give encouraging feedback
- Use Socratic method: ask questions that lead the student to discover the answer
- Return response as valid JSON with structure:
{
  "steps": [
    {
      "number": 1,
      "instruction": "what to do",
      "explanation": "why this step",
      "hint": "a hint without giving away the answer",
      "answer": "the result of this step"
    }
  ],
  "final_answer": "the complete solution",
  "key_concept": "the main concept being taught"
}"""


PER_STEP_PROMPT = """You are Mentis, an AI tutor. The student is working through a problem step by step.

Previous steps completed:
{completed_steps}

Current step to teach:
{current_step}

The student needs help with this step. Provide:
1. A brief explanation of what to do
2. A small hint if they're stuck
3. The answer only after they confirm they understand

Respond briefly and conversationally."""


class TutorService:
    def __init__(self, groq: GroqClient):
        self.groq = groq

    def generate_lesson(self, problem: dict, level: str = 'intermediate') -> dict:
        prompt = (
            f"Problem type: {problem.get('type', 'unknown')}\n"
            f"Problem content: {problem.get('content', '')}\n"
            f"Student level: {level}\n\n"
            f"Generate a complete step-by-step lesson. "
            f"Provide {self._step_count(level)} steps."
        )
        system = SYSTEM_PROMPT + f"\nStudent level: {level}"
        result = self.groq.reason(prompt, system=system)

        try:
            cleaned = result.strip()
            if cleaned.startswith('```json'):
                cleaned = cleaned.split('```json')[1].split('```')[0].strip()
            elif cleaned.startswith('```'):
                cleaned = cleaned.split('```')[1].split('```')[0].strip()
            return json.loads(cleaned)
        except (json.JSONDecodeError, IndexError):
            return {
                'steps': [{'number': 1, 'instruction': result, 'explanation': '', 'hint': '', 'answer': ''}],
                'final_answer': '',
                'key_concept': '',
            }

    def get_step_help(self, problem: dict, completed: list, current: dict) -> str:
        prompt = PER_STEP_PROMPT.format(
            completed_steps='\n'.join(f"Step {s['number']}: {s['instruction']}" for s in completed),
            current_step=f"Step {current['number']}: {current['instruction']}",
        )
        return self.groq.reason(prompt)

    def _step_count(self, level: str) -> int:
        return {'beginner': 5, 'intermediate': 4, 'advanced': 3}.get(level, 4)
