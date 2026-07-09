"""Application-wide constants, enums, and lookup tables.

No business logic. No imports from other app modules.
"""

from enum import Enum
from typing import Final


# ── API ────────────────────────────────────────────────────────────────

API_V1_PREFIX: Final[str] = '/api/v1'
API_DEFAULT_PAGE_SIZE: Final[int] = 20
API_MAX_PAGE_SIZE: Final[int] = 100

# ── Time ───────────────────────────────────────────────────────────────

SECONDS_IN_MINUTE: Final[int] = 60
MINUTES_IN_HOUR: Final[int] = 60
HOURS_IN_DAY: Final[int] = 24
SECONDS_IN_HOUR: Final[int] = SECONDS_IN_MINUTE * MINUTES_IN_HOUR
SECONDS_IN_DAY: Final[int] = SECONDS_IN_HOUR * HOURS_IN_DAY
MICROSECONDS_IN_SECOND: Final[int] = 1_000_000

# ── HTTP ───────────────────────────────────────────────────────────────

HTTP_STATUS_OK: Final[int] = 200
HTTP_STATUS_CREATED: Final[int] = 201
HTTP_STATUS_NO_CONTENT: Final[int] = 204
HTTP_STATUS_BAD_REQUEST: Final[int] = 400
HTTP_STATUS_UNAUTHORIZED: Final[int] = 401
HTTP_STATUS_FORBIDDEN: Final[int] = 403
HTTP_STATUS_NOT_FOUND: Final[int] = 404
HTTP_STATUS_CONFLICT: Final[int] = 409
HTTP_STATUS_UNPROCESSABLE_ENTITY: Final[int] = 422
HTTP_STATUS_TOO_MANY_REQUESTS: Final[int] = 429
HTTP_STATUS_INTERNAL_SERVER_ERROR: Final[int] = 500
HTTP_STATUS_BAD_GATEWAY: Final[int] = 502

# ── Teaching ───────────────────────────────────────────────────────────


class Subject(str, Enum):
    MATH = 'math'
    PHYSICS = 'physics'
    CHEMISTRY = 'chemistry'
    BIOLOGY = 'biology'
    CODING = 'coding'
    GENERAL = 'general'


class Difficulty(str, Enum):
    BEGINNER = 'beginner'
    INTERMEDIATE = 'intermediate'
    ADVANCED = 'advanced'


class TeachingLanguage(str, Enum):
    HINGLISH = 'hinglish'
    HINDI = 'hindi'
    ENGLISH = 'english'


class TeacherTone(str, Enum):
    WARM_AND_PATIENT = 'warm_and_patient'
    STRICT_BUT_FAIR = 'strict_but_fair'
    ENCOURAGING = 'encouraging'
    FUN_AND_ENERGETIC = 'fun_and_energetic'


class StudentLevel(str, Enum):
    SCHOOL = 'school'
    COLLEGE = 'college'
    PROFESSIONAL = 'professional'


class LessonPhase(str, Enum):
    OBSERVE = 'observe'
    CONCEPT = 'concept'
    PREREQUISITE = 'prerequisite'
    EXAMPLE = 'example'
    STEP_BY_STEP = 'step_by_step'
    CHECKPOINT = 'checkpoint'
    HINT = 'hint'
    CORRECTION = 'correction'
    SUMMARY = 'summary'
    HOMEWORK = 'homework'
    QUIZ = 'quiz'
    REVISION = 'revision'


# ── Learning & Memory ─────────────────────────────────────────────────


class ConfidenceLevel(str, Enum):
    VERY_LOW = 'very_low'
    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'
    VERY_HIGH = 'very_high'


class MistakeType(str, Enum):
    CONCEPTUAL = 'conceptual'
    CALCULATION = 'calculation'
    CARELESS = 'careless'
    MISUNDERSTANDING = 'misunderstanding'


class KnowledgeEdgeType(str, Enum):
    PREREQUISITE = 'prerequisite'
    BUILD_ON = 'build_on'
    RELATED = 'related'
    EXAMPLE_OF = 'example_of'


# ── AR ─────────────────────────────────────────────────────────────────


class ARAnchorType(str, Enum):
    WORLD = 'world'
    IMAGE = 'image'
    PLANE = 'plane'
    FACE = 'face'
    OBJECT = 'object'


class ARShape(str, Enum):
    CIRCLE = 'circle'
    ARROW = 'arrow'
    LINE = 'line'
    RECTANGLE = 'rectangle'
    HIGHLIGHT = 'highlight'
    POINTER = 'pointer'
    UNDERLINE = 'underline'
    HANDWRITING = 'handwriting'
    EQUATION = 'equation'
    GRAPH = 'graph'
    GEOMETRY = 'geometry'
    OBJECT_3D = '3d_object'


class ARAnimationType(str, Enum):
    FADE_IN = 'fade_in'
    DRAW = 'draw'
    PULSE = 'pulse'
    BOUNCE = 'bounce'
    GLOW = 'glow'
    NONE = 'none'


# ── Speech ─────────────────────────────────────────────────────────────


class SpeechEmotion(str, Enum):
    NEUTRAL = 'neutral'
    HAPPY = 'happy'
    ENCOURAGING = 'encouraging'
    SURPRISED = 'surprised'
    THINKING = 'thinking'
    PATIENT = 'patient'
    EXCITED = 'excited'
    SERIOUS = 'serious'


class SpeechSpeed(str, Enum):
    VERY_SLOW = 'x-slow'
    SLOW = 'slow'
    NORMAL = 'medium'
    FAST = 'fast'
    VERY_FAST = 'x-fast'


# ── Agent Names ────────────────────────────────────────────────────────


class AgentName(str, Enum):
    VISION = 'vision_agent'
    PLANNER = 'planner_agent'
    TEACHER = 'teacher_agent'
    CRITIC = 'critic_agent'
    AR = 'ar_agent'
    SPEECH = 'speech_agent'
    MEMORY = 'memory_agent'
    COMPOSER = 'response_composer'


# ── Hinglish Teaching Phrases ──────────────────────────────────────────

HINGLISH_ENCOURAGEMENTS: Final[list[str]] = [
    'Bahut badhiya!',
    'Shabash!',
    'Aapne sahi kiya!',
    'Ek dum perfect!',
    'Wah! Kya baat hai!',
    'Maza aa gaya!',
    'Aap to genius ho!',
    'Excellent beta!',
    'Very good!',
    'Keep it up!',
]

HINGLISH_TRANSITIONS: Final[list[str]] = [
    'Toh dekhte hain',
    'Chaliye aage badhte hain',
    'Ab hum next step dekhte hain',
    'Toh aisa karte hain',
    'Ab main aapko batata hoon',
    'Dhyan se dekho',
    'Ek baar aur samajhte hain',
    'Toh yahan se shuru karte hain',
]

HINGLISH_CHECKPOINTS: Final[list[str]] = [
    'Samajh aa raha hai?',
    'Koi doubt hai?',
    'Clear hai na?',
    'Aapko samajh mein aaya?',
    'Kya aap next step bata sakte hain?',
    'Thoda confusion hai kya?',
    'Sab kuch theek hai?',
]

# ── LLM Provider Configuration ─────────────────────────────────────────

LLM_MAX_RETRIES: Final[int] = 3
LLM_RETRY_DELAY_SECONDS: Final[float] = 1.0
LLM_TIMEOUT_SECONDS: Final[int] = 60
