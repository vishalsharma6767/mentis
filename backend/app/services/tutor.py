import json
from app.services.groq_client import GroqClient


SYSTEM_PROMPT = """You are Mentis, an AI tutor. You teach step by step without giving answers immediately.
- Adapt explanations to the student's level (beginner, intermediate, advanced)
- Break problems into small logical steps
- Ask guiding questions before revealing answers
- Praise progress and give encouraging feedback
- Use Socratic method: ask questions that lead the student to discover the answer
- Add AR overlay instructions that can be drawn over a notebook or textbook
- Include a quick check question after the lesson
- Return response as valid JSON with structure:
{
  "steps": [
    {
      "number": 1,
      "instruction": "what to do",
      "explanation": "why this step",
      "hint": "a hint without giving away the answer",
      "answer": "the result of this step",
      "ar_annotation": "short phrase to overlay on the page",
      "focus": "what region or symbol to highlight"
    }
  ],
  "final_answer": "the complete solution",
  "key_concept": "the main concept being taught",
  "confidence_check": "one question to ask the student",
  "recommended_practice": ["short practice recommendation"]
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


DOUBT_PROMPT = """You are Mentis in a live tutoring session.
The student asked a doubt while solving this material.

Learning mode: {mode}
Student level: {level}
Problem:
{content}

Current step:
{current_step}

Student doubt:
{question}

Answer like a real teacher:
- brief and conversational
- do not dump the final answer unless necessary
- give one AR pen annotation phrase to write on the page
- ask one follow-up question

Return only valid JSON:
{{
  "reply": "teacher response",
  "pen_annotation": "short text to write with AR pen",
  "follow_up": "question for student"
}}"""


class TutorService:
    def __init__(self, groq: GroqClient):
        self.groq = groq

    def generate_lesson(self, problem: dict, level: str = 'intermediate', mode: str = 'math') -> dict:
        prompt = (
            f"Learning mode: {mode}\n"
            f"Problem type: {problem.get('type', 'unknown')}\n"
            f"Problem content: {problem.get('content', '')}\n"
            f"Student level: {level}\n\n"
            f"Generate a complete step-by-step lesson. "
            f"Provide {self._step_count(level)} steps."
        )
        system = SYSTEM_PROMPT + f"\nStudent level: {level}\nLearning mode: {mode}"
        try:
            result = self.groq.reason(prompt, system=system)
        except Exception:
            return self._fallback_lesson(problem, level, mode)

        try:
            cleaned = result.strip()
            if cleaned.startswith('```json'):
                cleaned = cleaned.split('```json')[1].split('```')[0].strip()
            elif cleaned.startswith('```'):
                cleaned = cleaned.split('```')[1].split('```')[0].strip()
            return json.loads(cleaned)
        except (json.JSONDecodeError, IndexError):
            return {
                'steps': [{
                    'number': 1,
                    'instruction': result,
                    'explanation': '',
                    'hint': '',
                    'answer': '',
                    'ar_annotation': 'Focus here',
                    'focus': 'problem area',
                }],
                'final_answer': '',
                'key_concept': '',
                'confidence_check': 'Can you explain the next step in your own words?',
                'recommended_practice': ['Try one similar question without looking at the answer.'],
            }

    def get_step_help(self, problem: dict, completed: list, current: dict) -> str:
        prompt = PER_STEP_PROMPT.format(
            completed_steps='\n'.join(f"Step {s['number']}: {s['instruction']}" for s in completed),
            current_step=f"Step {current['number']}: {current['instruction']}",
        )
        return self.groq.reason(prompt)

    def answer_doubt(
        self,
        content: str,
        question: str,
        current_step: dict | None = None,
        level: str = 'intermediate',
        mode: str = 'math',
    ) -> dict:
        step_text = 'No step selected'
        if current_step:
            step_text = f"Step {current_step.get('number', '')}: {current_step.get('instruction', '')}"
        prompt = DOUBT_PROMPT.format(
            mode=mode,
            level=level,
            content=content,
            current_step=step_text,
            question=question,
        )
        try:
            result = self.groq.reason(prompt)
            cleaned = result.strip()
            if cleaned.startswith('```json'):
                cleaned = cleaned.split('```json')[1].split('```')[0].strip()
            elif cleaned.startswith('```'):
                cleaned = cleaned.split('```')[1].split('```')[0].strip()
            return json.loads(cleaned)
        except Exception:
            return {
                'reply': 'Good doubt. Look at the current step and ask what operation keeps both sides or both ideas balanced.',
                'pen_annotation': 'Why this step?',
                'follow_up': 'Can you tell me what changed from the previous line?',
            }

    def _step_count(self, level: str) -> int:
        return {'beginner': 5, 'intermediate': 4, 'advanced': 3}.get(level, 4)

    def _fallback_lesson(self, problem: dict, level: str, mode: str) -> dict:
        content = problem.get('content') or 'the scanned problem'
        labels = {
            'math': ('Identify the unknown', 'Look for the variable and what the question asks.'),
            'coding': ('Read the error or goal', 'Find the line, function, or output the code is about.'),
            'science': ('Name the concept', 'Identify the formula, component, or process being tested.'),
            'book': ('Find the main idea', 'Underline the sentence that carries the paragraph.'),
            'language': ('Understand the sentence', 'Spot the subject, verb, and unfamiliar words.'),
            'diagram': ('Label the parts', 'Start with the most obvious label or relationship.'),
            'homework': ('Sort the questions', 'Begin with the easiest question to build momentum.'),
        }
        first_instruction, first_hint = labels.get(mode, labels['math'])
        return {
            'steps': [
                {
                    'number': 1,
                    'instruction': first_instruction,
                    'explanation': f'Before solving, Mentis anchors the lesson to what is visible: {content[:140]}.',
                    'hint': first_hint,
                    'answer': 'The target is the main question or unclear concept.',
                    'ar_annotation': 'Circle the target',
                    'focus': 'main problem area',
                },
                {
                    'number': 2,
                    'instruction': 'Break it into one small move',
                    'explanation': 'A good tutor does not jump to the final answer. We choose the smallest valid next step.',
                    'hint': 'Ask: what can I simplify, label, translate, or test first?',
                    'answer': 'Write the next operation, label, translation, or test beside the original work.',
                    'ar_annotation': 'Next small step',
                    'focus': 'first working line',
                },
                {
                    'number': 3,
                    'instruction': 'Check your reasoning',
                    'explanation': 'Compare the new line with the original problem so mistakes are caught early.',
                    'hint': 'Does the meaning stay the same after your step?',
                    'answer': 'If it matches, continue. If not, revise the previous step.',
                    'ar_annotation': 'Check before moving on',
                    'focus': 'student answer',
                },
            ],
            'final_answer': 'Continue step by step with the same reasoning pattern.',
            'key_concept': f'{mode.title()} guided problem solving',
            'confidence_check': 'What was the reason for the first step?',
            'recommended_practice': [
                'Solve one similar example slowly.',
                'Say each step out loud before writing it.',
            ],
        }
