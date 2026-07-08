from app.services.groq_client import GroqClient
from app.services.vision import VisionService
from app.services.tutor import TutorService

groq_client = GroqClient()
vision_service = VisionService(groq_client)
tutor_service = TutorService(groq_client)

__all__ = ['groq_client', 'vision_service', 'tutor_service']
