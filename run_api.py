"""FastAPI 서버 실행."""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "tutor_agent.platforms.api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
