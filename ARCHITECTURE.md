# ARCHITECTURE.md — 시스템 아키텍처 및 데이터 흐름

본 문서는 **GitHub MCP 에이전트 학습용 예제 프로젝트**의 시스템 구조와 모듈 간 상호작용, 특히 LangChain 기반의 3단계 Fallback 처리 매커니즘을 상세히 설명합니다.

---

## 🏗️ 전체 시스템 구조도 (System Architecture)

시스템은 단일 사용자 디바이스 혹은 로컬 개발 서버 환경 내에서 **FastAPI 백엔드**와 **Vite+React 프론트엔드**가 협력하여 구동되며, 외부의 **GitHub API**, **Slack SDK**, **로컬 파일 시스템(Local File System)** 및 여러 **LLM API**들과 연동됩니다.

```text
+-----------------------------------------------------------------------------------+
|                                  사용자 (User)                                    |
+-----------------------------------------------------------------------------------+
                                         │  ▲ 자연어 명령 입력 & 챗봇 응답
                                         ▼  │
+-----------------------------------------------------------------------------------+
|                        React 프론트엔드 (frontend/src/Chat.tsx)                     |
+-----------------------------------------------------------------------------------+
                                         │  ▲ REST API (/agent/task)
                                         ▼  │
+-----------------------------------------------------------------------------------+
|                         FastAPI 백엔드 (backend/main.py)                          |
|  +-----------------------------------+     +-----------------------------------+  |
|  | 1. LLM Router (llm_router.py)    |     | 2. MCP Tool Executor              |  |
|  |    - 플랜 수립 & 최종 답변 조율   |     |    - 도구 순차 실행 (tools/__init__.py)|  |
|  +-----------------------------------+     +-----------------------------------+  |
+-----------------------------------------------------------------------------------+
                 │                                   │          │            │
                 │ 3단계 Fallback 엔진               │ PyGithub │ Slack SDK  │ File I/O
                 ▼                                   ▼          ▼            ▼
+------------------------------------+       +------------+ +-------+ +--------------+
|     LangChain Fallback Engine      |       | GitHub API | | Slack | | Local File   |
|  ┌──────────────────────────────┐  |       +------------+ +-------+ | System       |
|  │ Primary: Gemini 2.5 Flash    │  |                                +--------------+
|  └──────────────┬───────────────┘  |
|                 │ Quota 초과 시 Failover
|  ┌──────────────▼───────────────┐  |
|  │ Secondary: Groq Llama 3.3 70B│  |
|  └──────────────┬───────────────┘  |
|                 │ 연결 장애 시 Failover
|  ┌──────────────▼───────────────┐  |
|  │ Tertiary: Local Ollama Gemma │  |
|  └──────────────────────────────┘  |
+------------------------------------+
```

<details>
<summary>📐 Mermaid 다이어그램으로 보기 (클릭하여 펼치기)</summary>

```mermaid
graph TD
    User["사용자"] <-->|자연어 명령 입력| Frontend["React Frontend (Chat.tsx)"]
    Frontend <-->|POST /agent/task| Backend["FastAPI Backend (main.py)"]
    
    subgraph Backend_App ["FastAPI 백엔드"]
        Backend -->|1. 플랜 수립 & 3. 답변 조율| LLMRouter["LLM Router (llm_router.py)"]
        Backend -->|2. 도구 순차 실행| MCP_Executor["MCP Tool Executor"]
    end
    
    subgraph LangChain_Fallback_Engine ["LangChain Fallback Engine"]
        LLMRouter -->|1순위| Gemini["Gemini 2.5 Flash"]
        Gemini -.->|Failover| Groq_Llama["Groq Llama 3.3 70B"]
        Groq_Llama -.->|Failover| Local_Ollama["Local Ollama Gemma"]
    end
    
    MCP_Executor <-->|PyGithub| GitHub_API["GitHub API"]
    MCP_Executor <-->|Slack SDK| Slack_API["Slack API"]
    MCP_Executor <-->|Path Safe I/O| Local_File["Local File System"]
```

</details>

---

## 🔄 핵심 에이전트 루프 흐름 (Agent Loop Flow)

사용자가 입력창에 자연어로 요청(예: *"notes.txt 파일 내용을 읽고 요약 결과를 result.md에 저장해줘"*)을 보냈을 때 백엔드 내부에서 동작하는 상세 라이프사이클입니다.

### 📌 텍스트 기반 순차 흐름도

1. **[사용자 ➔ 프론트엔드]**: 자연어 요청 입력 (`"notes.txt 읽고 result.md에 요약 저장해줘"`)
2. **[프론트엔드 ➔ 백엔드]**: `POST /agent/task` 요청 전달
3. **[1단계: Planner]**:
   - 백엔드가 `mcp/*.json` 스펙들(`github.json`, `slack.json`, `local_file.json`)과 사용자 요청을 **LLM Router**에 전달
   - LangChain Fallback (Gemini ➔ Groq Llama ➔ Local Ollama)을 거쳐 **JSON 실행 플랜** 생성
4. **[2단계: Execution]**:
   - 백엔드가 JSON 플랜을 파싱하여 도구를 순차 실행
   - `read_local_file` 및 `write_local_file` 등 로컬 파일 제어 도구 또는 GitHub/Slack API 호출
   - 실행 결과 및 로그 기록
5. **[3단계: Synthesis]**:
   - 최초 요청과 실행 로그를 **LLM Router**에 전달하여 종합 요약 생성
6. **[백엔드 ➔ 프론트엔드 ➔ 사용자]**: 최종 답변 및 로그 전달, 화면 렌더링

<details>
<summary>📐 Mermaid 시퀀스 다이어그램으로 보기 (클릭하여 펼치기)</summary>

```mermaid
sequenceDiagram
    autonumber
    actor User as 사용자
    participant Front as React 프론트엔드
    participant Back as FastAPI 백엔드
    participant Router as LLM 라우터 (LangChain)
    participant Github as GitHub (PyGithub)
    
    User->>Front: 자연어 명령 입력 ("README.md 읽고 수정해줘")
    Front->>Back: POST /agent/task { description }
    
    Note over Back, Router: 1단계: Planner (플랜 수립)
    Back->>Router: 도구 스펙 + 사용자 요청 전달
    Router->>Router: Gemini -> Llama -> Ollama 순차 시도
    Router-->>Back: 실행 도구 시퀀스 (JSON Plan) 반환
    
    Note over Back, Github: 2단계: Execution (도구 실행)
    loop 각 도구 순차 실행
        Back->>Back: JSON Plan 파싱
        Back->>Github: PyGithub API 호출 (read_file, update_file 등)
        Github-->>Back: 실행 결과 데이터 반환
        Back->>Back: 실행 로그 기록
    end
    
    Note over Back, Router: 3단계: Synthesis (결과 요약)
    Back->>Router: 최초 요청 + 실행 로그 전달 (결과 요약 요청)
    Router-->>Back: 정중한 최종 피드백 생성
    
    Back-->>Front: 최종 결과 데이터 전달
    Front-->>User: 세부 로그 및 최종 챗봇 답변 렌더링
```

</details>

---

## 🛡️ 3단계 LLM Fallback 연동 아키텍처

본 프로젝트의 핵심 학습 포인트는 LangChain의 `with_fallbacks` 메소드를 결합한 고가용성 AI 모델 연동입니다.

1. **Gemini 2.5 Flash (Google)**:
   - **역할**: 주 분석 및 계획 생성(Primary).
   - **선정 이유**: 높은 토큰 윈도우와 빠른 속도, 우수한 JSON 스펙 준수율.
2. **Llama-3.3-70b-versatile (Groq)**:
   - **역할**: 1차 예비용 대형 LLM(Secondary).
   - **선정 이유**: 극도로 빠른 Groq Inference 속도와 준수한 추론 및 지시 이행 능력.
3. **gemma4:e2b (Local Ollama)**:
   - **역할**: 외부 네트워크 단절 또는 API 완전 장애 대응책(Tertiary).
   - **선정 이유**: 로컬 리소스만으로 작동하여 네트워크 에러나 API 키 유출 위험 없이 항상 작동을 보증.

### 예외 및 오류 전파 구조
- LangChain의 `with_fallbacks` 내부에서 각 LLM 커넥터의 예외 클래스(예: `google.api_core.exceptions.GoogleAPICallError`, `groq.APIConnectionError` 등)가 발생하면, 내부적으로 이를 가로채 다음 LLM 인스턴스의 `ainvoke`를 자동으로 촉발시킵니다.
- 최종적으로 3단계 모델마저 동작하지 못할 때에만 사용자에게 HTTP 500 에러를 전송하도록 격리 설계되었습니다.
