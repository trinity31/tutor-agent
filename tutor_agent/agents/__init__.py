"""TutorAgent 에이전트 패키지."""

import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

_MODEL_NAME = "gemini-2.5-flash"

# thinking(추론) 비활성 — gemini-2.5-flash는 기본 thinking이 켜져 있어 응답이
# 느리다(supervisor→전문에이전트 다단계라 지연 누적). 라우팅·개념 답변·과외엔
# 추론이 불필요하므로 꺼서 응답 속도를 크게 개선한다.
SUPERVISOR_MODEL = ChatGoogleGenerativeAI(model=_MODEL_NAME, thinking_budget=0)
SPECIALIST_MODEL = ChatGoogleGenerativeAI(model=_MODEL_NAME, thinking_budget=0)
# 퀴즈는 문항 품질을 위해 thinking 유지
QUIZ_MODEL = ChatGoogleGenerativeAI(model=_MODEL_NAME)

DEFAULT_MODEL = SPECIALIST_MODEL
