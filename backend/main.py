# 사전설치 : pip install fastapi uvicorn pydantic PyGithub python-dotenv langchain-google-genai langchain-groq langchain-ollama langchain-core slack_sdk
# 사전설치 : pip install langchain-ollama langgraph langchain-core fpdf2 requests
# 라이브러리를 독립적으로 사용하기 위해 가상환경(venv) 구성 : Ctrl + Shift + P --> Python:Select Interpreter --> create venv --> Python 3.12 선택
# 마크다운 파일을 보기 위한 Extension 설치(Ctrl + Shift + X 클릭) : Markdown Preview Mermaid Support 설치  --> md 파일 클릭 커서 이동 후 --> Ctrl + Shift + V로 확인
import os
import sys
import uvicorn
from dotenv import load_dotenv

# backend 디렉터리를 sys.path에 최우선 등록
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# 다른 모듈(tools_router, agent_router) import 전 .env 환경 변수 최우선 로드
dotenv_path = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(dotenv_path=dotenv_path)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.tools_router import router as tools_router
from routers.agent_router import router as agent_router
from routers.report_router import router as report_router


# FastAPI 애플리케이션 초기화
app = FastAPI(
    title="GitHub & Slack MCP 통합 에이전트 API",
    description="MCP 표준 규격을 준수하고 GitHub, Slack 등의 도구가 자동으로 병합되어 동작하는 통합 에이전트",
    version="2.0.0"
)

# CORS 설정 (프론트엔드 연동을 위해 모든 오리진 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 분리된 라우터 등록
app.include_router(tools_router)
app.include_router(agent_router)
app.include_router(report_router)


@app.get("/")
async def root():
    return {
        "message": "GitHub & Slack MCP 에이전트 API 서버가 정상 구동 중입니다.",
        "docs_url": "/docs",
        "tools_url": "/tools"
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
