from groq import Groq
from app.config import settings


class GroqClient:
    def __init__(self):
        self.client = Groq(api_key=settings.groq_api_key)
        self.vision_model = 'meta-llama/llama-4-scout-17b-16e-instruct'
        self.reasoning_model = 'llama-3.3-70b-versatile'

    def vision(self, image_data: str, prompt: str) -> str:
        completion = self.client.chat.completions.create(
            model=self.vision_model,
            messages=[
                {
                    'role': 'user',
                    'content': [
                        {'type': 'text', 'text': prompt},
                        {
                            'type': 'image_url',
                            'image_url': {'url': f'data:image/jpeg;base64,{image_data}'},
                        },
                    ],
                }
            ],
            max_tokens=4096,
        )
        return completion.choices[0].message.content or ''

    def reason(self, prompt: str, system: str = '') -> str:
        messages = []
        if system:
            messages.append({'role': 'system', 'content': system})
        messages.append({'role': 'user', 'content': prompt})

        completion = self.client.chat.completions.create(
            model=self.reasoning_model,
            messages=messages,
            max_tokens=4096,
            temperature=0.7,
        )
        return completion.choices[0].message.content or ''

    def stream_reason(self, prompt: str, system: str = ''):
        messages = []
        if system:
            messages.append({'role': 'system', 'content': system})
        messages.append({'role': 'user', 'content': prompt})

        stream = self.client.chat.completions.create(
            model=self.reasoning_model,
            messages=messages,
            max_tokens=4096,
            temperature=0.7,
            stream=True,
        )
        for chunk in stream:
            content = chunk.choices[0].delta.content
            if content:
                yield content
