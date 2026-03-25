"""TutorAgent 에이전트 패키지."""

import os
from dotenv import load_dotenv

load_dotenv()

# 모델 설정 (create_agent에 문자열로 전달)
SUPERVISOR_MODEL = "google_genai:gemini-2.5-flash"
SPECIALIST_MODEL = "google_genai:gemini-2.5-flash"

DEFAULT_MODEL = SPECIALIST_MODEL
