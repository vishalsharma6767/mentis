"""Dialogue Management Agent.

Maintains conversation state across turns within a lesson.
Tracks: current step, student utterances, what was taught,
what the student understood/didn't, and the overall flow.
"""

from collections import deque
from typing import Any, Optional

from app.ai.teacher.emotion import EmotionState, detect_emotion
from app.ai.teacher.schemas import CoachingSignal, LessonStep, StudentContext
from app.core.logger import get_logger

log = get_logger(__name__)


class TurnRecord:
    """A single exchange in the dialogue."""

    def __init__(
        self,
        student_message: str,
        teacher_response: str,
        step_index: int,
        emotion: str = EmotionState.NEUTRAL,
        emotion_confidence: float = 0.0,
    ) -> None:
        self.student_message = student_message
        self.teacher_response = teacher_response
        self.step_index = step_index
        self.emotion = emotion
        self.emotion_confidence = emotion_confidence


class DialogueManager:
    """Manages the conversational flow within a single lesson session."""

    def __init__(self, max_history: int = 30) -> None:
        self._turns: deque[TurnRecord] = deque(maxlen=max_history)
        self._current_step: int = 0
        self._total_steps: int = 0
        self._topic: str = ''
        self._consecutive_correct: int = 0
        self._consecutive_wrong: int = 0
        self._help_requests: int = 0

    def start_lesson(self, total_steps: int, topic: str) -> None:
        """Initialise dialogue state for a new lesson."""
        self._turns.clear()
        self._current_step = 0
        self._total_steps = total_steps
        self._topic = topic
        self._consecutive_correct = 0
        self._consecutive_wrong = 0
        self._help_requests = 0

    @property
    def current_step(self) -> int:
        return self._current_step

    @current_step.setter
    def current_step(self, value: int) -> None:
        self._current_step = max(0, min(value, self._total_steps - 1))

    def advance_step(self, steps: int = 1) -> None:
        self.current_step += steps

    def record_turn(
        self,
        student_message: str,
        teacher_response: str,
        emotion: Optional[str] = None,
        emotion_confidence: float = 0.0,
    ) -> TurnRecord:
        """Record a student ↔ teacher exchange."""
        record = TurnRecord(
            student_message=student_message,
            teacher_response=teacher_response,
            step_index=self._current_step,
            emotion=emotion or EmotionState.NEUTRAL,
            emotion_confidence=emotion_confidence,
        )
        self._turns.append(record)

        # Track correctness heuristics
        lower = student_message.lower()
        if any(m in lower for m in ['correct', 'right', 'yes', 'got it', 'samajh aaya', 'understood']):
            self._consecutive_correct += 1
            self._consecutive_wrong = 0
        elif any(m in lower for m in ['wrong', 'no', 'nhi', 'nahi', 'not', 'don\'t understand']):
            self._consecutive_wrong += 1
            self._consecutive_correct = 0

        if any(m in lower for m in ['help', 'explain again', 'बताओ', 'doubt', 'samjhao']):
            self._help_requests += 1

        return record

    def get_context_summary(self) -> dict[str, Any]:
        """Build a compact summary of the conversation so far."""
        recent = list(self._turns)[-5:]
        return {
            'turns_taken': len(self._turns),
            'current_step': self._current_step,
            'total_steps': self._total_steps,
            'topic': self._topic,
            'consecutive_correct': self._consecutive_correct,
            'consecutive_wrong': self._consecutive_wrong,
            'help_requests': self._help_requests,
            'recent_emotions': [t.emotion for t in recent],
            'last_student_message': recent[-1].student_message if recent else '',
            'last_teacher_response': recent[-1].teacher_response if recent else '',
        }

    def to_system_context(self) -> str:
        """Format the dialogue state for injection into agent prompts."""
        ctx = self.get_context_summary()
        if ctx['turns_taken'] == 0:
            return 'This is the start of the lesson. No prior conversation.'

        return f"""Conversation so far ({ctx['turns_taken']} turns):
- Current step: {ctx['current_step'] + 1}/{ctx['total_steps']}
- Topic: {ctx['topic']}
- Student momentum: {ctx['consecutive_correct']} correct / {ctx['consecutive_wrong']} wrong in a row
- Help requests: {ctx['help_requests']}
- Recent emotions: {', '.join(ctx['recent_emotions']) or 'neutral'}
- Last student said: "{ctx['last_student_message']}"
- Teacher last said: "{ctx['last_teacher_response'][:100]}..."
"""
