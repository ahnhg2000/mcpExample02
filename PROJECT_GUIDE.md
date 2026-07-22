# mcpExample 프로젝트 전체 설명서 및 아키텍처 가이드

본 문서는 `mcpExample` 프로젝트의 **전체 구조**, **React 프론트엔드와 FastAPI 백엔드 간의 흐름도**, 그리고 **MCP(Model Context Protocol)** 및 **Skill(스킬)** 기능의 핵심 파일과 함수에 대해 직관적이고 상세하게 정리한 종합 개발 가이드입니다.

---

## 1. 전체 프로젝트 구조 및 개요

`mcpExample` 프로젝트는 **React(Vite + TypeScript)** 기반의 웹 대화형 UI와 **FastAPI + PyGithub + LangChain** 기반의 AI 백엔드가 결합하여, 사용자의 자연어 명령에 따라 깃허브(GitHub) 작업을 자동 계획 및 실행하는 에이전트 시스템입니다.

### 디렉터리 및 주요 파일 구조

```
mcpExample02/
├── 📄 PROJECT_GUIDE.md        # [본 파일] 프로젝트 전체 종합 설명서
├── 📄 README.md               # 프로젝트 기본 안내 문서
├── 📄 ARCHITECTURE.md         # 백엔드 및 3단계 Fallback 시스템 구조 설명서
├── 📄 DESIGN.md               # 프론트엔드 UX/UI 디자인 스펙 정의서
├── 📄 AGENTS.md               # 에이전트 행동 지침 및 규칙 파일
├── 📄 .env                    # API 키 설정 파일 (GITHUB_TOKEN, SLACK_BOT_TOKEN, GOOGLE_API_KEY, GROQ_API_KEY)
│
├── 📂 backend/                # FastAPI 기반 Python 백엔드
│   ├── 📄 main.py             # FastAPI 메인 서버 엔드포인트
│   ├── 📄 llm_router.py       # LangChain 3단계 Fallback LLM 라우터
│   ├── 📄 mcp_loader.py       # mcp/*.json 스펙 자동 카탈로그 로더
│   ├── 📄 requirements.txt    # 백엔드 의존성 라이브러리 목록
│   ├── 📂 routers/            # FastAPI 라우터 모듈 (agent_router.py, tools_router.py)
│   └── 📂 tools/              # MCP 도구 백엔드 실행 모듈
│       ├── 📄 __init__.py      # 통합 도구 디스패처 (execute_tool)
│       ├── 📄 github_tools.py  # GitHub API 처리 모듈 (6개 도구)
│       ├── 📄 slack_tools.py   # Slack SDK 처리 모듈 (3개 도구)
│       └── 📄 local_file_tools.py # [NEW] 로컬 파일 읽기/쓰기 처리 모듈 (2개 도구)
│
├── 📂 frontend/               # React + Vite + TailwindCSS 프론트엔드
│   ├── 📄 package.json        # Node.js 패키지 및 의존성 설정
│   └── 📂 src/
│       ├── 📄 App.tsx         # 메인 애플리케이션 컴포넌트
│       ├── 📄 main.tsx        # React 엔트리포인트
│       ├── 📄 index.css       # TailwindCSS 스타일 정의
│       └── 📂 components/
│           └── 📄 Chat.tsx    # 대화형 대시보드 UI 및 MCP 도구 스펙 보기 컴포넌트
│
├── 📂 mcp/                    # MCP (Model Context Protocol) 표준 스펙 정의
│   ├── 📄 github.json         # 6개 GitHub MCP 도구 사양 정의 파일
│   ├── 📄 slack.json          # 3개 Slack MCP 도구 사양 정의 파일
│   └── 📄 local_file.json     # 2개 로컬 파일 읽기/쓰기 MCP 도구 사양 정의 파일
│
└── 📂 skills/                 # 에이전트 스킬 지침서
    └── 📄 github.md           # 깃허브 자동 반영 스킬 지침 및 MCP vs Skill 비교 분석서
```

---

## 2. React Front ↔ FastAPI Backend 전체 흐름도

사용자가 프론트엔드 화면에서 "현재 로컬 변경 사항을 깃허브에 반영해줘" 또는 "결과를 notes.txt 파일에 저장해줘"와 같은 자연어를 입력했을 때, 백엔드를 거쳐 최종 응답이 화면에 출력되기까지의 **End-to-End 전체 흐름도**입니다.

### 시스템 처리 프로세스 흐름 (End-to-End)

```text
[1. 사용자 입력] ──> [2. React 프론트엔드] ──> [3. FastAPI 백엔드]
                                                     │
                       ┌─────────────────────────────┴─────────────────────────────┐
                       ▼                                                           ▼
         [방식 A. MCP 표준 도구 탐색]                                [방식 B. Skill 프롬프트 지침]
         (mcp/*.json 스펙 자동 로드:                                (skills/github.md 지침 참조)
          GitHub, Slack, Local File)
                       │                                                           │
                       └─────────────────────────────┬─────────────────────────────┘
                                                     ▼
                                      [4. LLM 라우터 (llm_router.py)]
                                       (Gemini -> Groq -> Ollama)
                                                     │
                                                     ▼
                                [5. 백엔드 자율 도구 실행 (backend/tools/)]
         ┌───────────────────────────────────┼───────────────────────────────────┐
         ▼                                   ▼                                   ▼
 [GitHub 작업 자율 실행]             [Slack 메시지/파일 전송]            [로컬 파일 읽기/쓰기 실행]
 (PyGithub 및 Git CLI)               (Slack SDK API)                     (local_file_tools.py)
                                                     │
                                                     ▼
                                      [6. 최종 보고서 마크다운 출력]
```

#### 단계별 세부 처리 절차

| 단계 | 수행 주체 | 상세 처리 내용 |
| :---: | :--- | :--- |
| **1단계** | **사용자 ➔ Front** | 사용자가 React 화면 입력창에 `"notes.txt 파일 내용 읽어서 요약해줘"`와 같은 자연어 명령을 입력하고 전송합니다. |
| **2단계** | **Front ➔ Back** | 프론트엔드(`Chat.tsx`)에서 백엔드(`agent_router.py`)의 `POST /agent/task` 엔드포인트로 자연어 요청을 전송합니다. |
| **3단계** | **Back (MCP vs Skill)** | 백엔드는 요청 성격에 따라 두 가지 도구 접근 방식을 병행하여 참조합니다.<br/>• **MCP 방식**: `mcp_loader.py`를 통해 `mcp/*.json` (`github.json`, `slack.json`, `local_file.json`) 도구 카탈로그를 자동 로드하여 참조<br/>• **Skill 방식**: `skills/github.md`에 정의된 Git 실행 프롬프트 수칙 및 지침서 참조 |
| **4단계** | **LLM Router** | `llm_router.py`가 3단계 Fallback(Gemini ➔ Groq ➔ Ollama)에 따라 최적의 LLM을 호출하고 실행 계획 및 도구 호출 파라미터를 생성합니다. |
| **5단계** | **도구 실행 레이어** | `backend/tools/__init__.py`의 `execute_tool` 디스패처가 호출되어 GitHub (`github_tools.py`), Slack (`slack_tools.py`), 로컬 파일 (`local_file_tools.py`) 도구를 안전하게 자율 실행합니다. |
| **6단계** | **Back ➔ Front** | 도구 실행 결과 및 요약 텍스트를 조합하여 최종 **마크다운 보고서**를 생성하고 프론트엔드 대화창에 출력합니다. |

---

## 3. MCP (Model Context Protocol) 세부 설명

### MCP 개념
MCP는 AI 모델이 외부 시스템(데이터베이스, 깃허브, Slack, 로컬 파일 시스템 등)의 기능(Tool)을 **표준화된 규격(JSON-RPC 기반 API)**으로 안전하게 탐색하고 호출할 수 있도록 해주는 백엔드 프로토콜입니다.

---

### 1) MCP 스펙 파일 목록 (`mcp/*.json`)

MCP 규격에 맞춰 에이전트가 사용할 수 있는 도구의 사양과 파라미터(Input Schema)가 정의되어 있습니다.

#### 📂 [local_file.json](file:///c:/aiproject/mcpExample02/mcp/local_file.json) (로컬 파일 제어 도구)
| 도구명 (Tool Name) | 설명 | 주요 입력 파라미터 (Input Schema) |
| :--- | :--- | :--- |
| `read_local_file` | 지정한 로컬 파일의 텍스트 내용을 읽어옵니다. | `file_path` (읽어올 상대 경로 또는 프로젝트 기준 경로) |
| `write_local_file` | 지정한 로컬 파일 경로에 텍스트 내용을 작성하거나 덮어씁니다. (없으면 자동 생성) | `file_path` (저장 경로), `content` (기록할 텍스트 내용) |

#### 📂 [github.json](file:///c:/aiproject/mcpExample02/mcp/github.json) (GitHub 연동 도구)
| 도구명 (Tool Name) | 설명 | 주요 입력 파라미터 (Input Schema) |
| :--- | :--- | :--- |
| `list_repositories` | 사용자 GitHub 계정의 저장소 목록을 최대 10개까지 조회합니다. | 없음 |
| `get_repository_details` | 특정 저장소의 별 개수, 설명, 주 언어, 포크 수 등의 정보를 조회합니다. | `repo_name` (저장소명) |
| `read_file_content` | 원격 저장소 내 지정한 경로의 파일 내용(UTF-8)을 읽어옵니다. | `repo_name`, `path` |
| `create_or_update_file` | 저장소 내에 파일이 없으면 신규 생성하고, 있으면 내용을 업데이트하여 커밋합니다. | `repo_name`, `path`, `content`, `commit_message` |
| `list_commits` | 지정한 저장소의 최근 커밋 내역(SHA, 작성자, 메시지, 날짜)을 조회합니다. | `repo_name`, `limit` (기본값: 5) |
| `push_all_changes` | **[핵심 종합 도구]** 로컬 Git의 추가/수정/삭제 파일을 자동 파싱하여 `git add .`, 커밋 메시지 자동 생성, `git commit`, `git push` 및 마크다운 보고서를 자동 반환합니다. | `commit_message` (선택 사항) |

#### 📂 [slack.json](file:///c:/aiproject/mcpExample02/mcp/slack.json) (Slack 연동 도구)
| 도구명 (Tool Name) | 설명 | 주요 입력 파라미터 (Input Schema) |
| :--- | :--- | :--- |
| `send_slack_message` | Slack 채널에 메시지 또는 커스텀 블록을 전송합니다. | `channel`, `message`, `blocks` |
| `list_slack_channels` | 사용 가능한 Slack 채널 목록을 조회합니다. | 없음 |
| `upload_file_to_slack` | Slack 채널에 로컬 파일을 업로드합니다. | `channel`, `file_path`, `comment` |

---

### 2) 백엔드 코어 파이썬 파일 및 핵심 함수

#### [local_file_tools.py](file:///c:/aiproject/mcpExample02/backend/tools/local_file_tools.py)
로컬 파일 읽기 및 쓰기 도구의 실체 파이썬 로직이 구현된 모듈입니다.
* **`get_safe_target_path(project_root, rel_path)`**:
  * 상대 경로 및 절대 경로 입력을 해석한 후, 대상 경로가 프로젝트 루트 범위 내에 존재하는지 `os.path.commonpath`로 검증하여 상위 디렉터리 이탈(Directory Traversal) 공격을 엄격히 방지합니다.
* **`execute_local_file_tool(tool_name, arguments)`**:
  * `read_local_file`: 파일 존재 여부 및 디렉터리 여부를 확인한 후 UTF-8 텍스트 내용을 읽어 Markdown 포맷으로 반환합니다.
  * `write_local_file`: 상위 디렉터리가 없을 경우 자동 생성(`os.makedirs`) 후 텍스트를 기록하고 저장 결과 및 파일 크기를 반환합니다.

* **엔드포인트**:
  * `@app.get("/tools")`: 백엔드에 로드된 MCP 도구 목록(`MCP_TOOLS`)을 프론트엔드에 반환하는 MCP 규격 엔드포인트입니다.
  * `@app.post("/tools/call")`: 프론트엔드 또는 외부 시스템에서 요청한 도구 이름과 인자를 전달받아 실행하고, 표준 규격인 `{"content": [{"type": "text", "text": "..."}]}`로 반환합니다.
  * `@app.post("/agent/task")`: 사용자의 자연어 요청을 받아 **[1단계 계획 수립 ➔ 2단계 도구 순차 실행 ➔ 3단계 종합 보고서 생성]**의 전체 자율 에이전트 루프를 총괄합니다.

* **주요 함수 및 로직**:
  * `get_user_repo(repo_name: str)`: 
    * PyGithub를 이용해 Repository 객체를 가져옵니다.
    * 404 에러 발생 시 Python `difflib.get_close_matches` 알고리즘을 통한 **오타 자동 보정(Fuzzy Matching)**을 수행합니다. (예: `mcpExampel` 입력 시 `mcpExample`로 자동 교정)
  * `extract_json_array(text: str)`:
    * LLM 응답에 마크다운 코드 블록(```json)이 포함되어 있어도 정규표현식을 이용하여 순수 JSON 배열만 안전하게 디코딩합니다.
  * `push_all_changes` 내 Subprocess 로직:
    * `git status --porcelain` 명령으로 `Added(🟢)`, `Modified(🟡)`, `Deleted(🔴)` 상태를 각각 구분 파싱합니다.
    * 커밋 메시지가 지정되지 않은 경우 파일 변경 목록을 조합해 커밋 메시지(`feat/style: Add ... | Update ...`)를 자동 구성하고 `git add .` ➔ `git commit` ➔ `git push`를 연속 실행합니다.

---

#### [llm_router.py](file:///c:/aiproject/mcpExample/backend/llm_router.py)

LangChain 기반의 **3단계 견고한 Fallback(자동 장애 복구) LLM 라우터** 클래스입니다.

* **주요 클래스 및 함수**:
  * `LLMRouter`:
    * `self.gemini`: 1순위 모델 (`ChatGoogleGenerativeAI`, model: `gemini-2.5-flash`)
    * `self.groq_llama`: 2순위 모델 (`ChatGroq`, model: `llama-3.3-70b-versatile`)
    * `self.ollama_gemma`: 3순위 모델 (`ChatOllama`, model: `gemma4:e2b`, base_url: `http://localhost:11434`)
    * `self.fallback_chain = self.gemini.with_fallbacks([self.groq_llama, self.ollama_gemma])`: LangChain의 Fallback 기능으로 1순위 API 호출 실패 시 지연 없이 다음 모델로 자동 대체 실행됩니다.
  * `generate(system_prompt: str, user_prompt: str)`:
    * 비동기(ainvoke)로 체인을 실행하고 `response.response_metadata` 분석을 통해 **실제로 어떤 LLM 모델이 응답을 처리했는지** 파악하여 튜플 `(응답텍스트, 모델표시명)` 형태로 반환합니다.

---

## 4. Skill (스킬) 세부 설명 및 MCP와의 비교 분석

### Skill 개념
Skill(스킬)은 백엔드 코드 작성이나 웹 API 등록 없이, 에이전트의 프롬프트 지침 문서(Markdown)에 행동 순서와 규칙을 명시함으로써 에이전트가 로컬 터미널 명령 도구(`run_command` 등)를 이용해 자율적으로 작업을 완수하도록 가이드하는 프롬프트 엔지니어링 방식입니다.

---

### 1) Skill 파일: [github.md](file:///c:/aiproject/mcpExample/skills/github.md)
에이전트에게 깃허브 반영 업무를 부여할 때 참고하도록 작성된 지침서 문서입니다.

* **주요 구성**:
  * `[ROLE: GIT_REFLECT_SKILL]`: 에이전트 역할 정의.
  * `[ACTION STEPS]`:
    1. 로컬 저장소 상태 확인 (`git status --porcelain`)
    2. 변경 파일 분류 (추가, 수정, 삭제)
    3. 소스 코드 스테이징 (`git add .`)
    4. 커밋 메시지 자동 수립
    5. 커밋 및 푸시 수행 (`git commit`, `git push origin main`)
    6. 완료 보고서 양식에 맞춘 결과 출력

---

### 2) MCP vs Skill 방식 정밀 비교

| 비교 항목 | 🔌 MCP (Model Context Protocol) 방식 | 📜 Skill (스킬) 지침 방식 |
| :--- | :--- | :--- |
| **아키텍처** | 백엔드 API 서버 (FastAPI 등) 기반 | 에이전트 프롬프트 지침서 (Markdown) 기반 |
| **실행 주체** | 백엔드 파이썬 코드 및 PyGithub API / Subprocess | 에이전트 자율 루프 (로컬 쉘 `run_command` 연동) |
| **확장 방식** | 백엔드 코드 작성 및 `mcp/github.json` 등록 필요 | `skills/*.md` 파일 작성만으로 즉시 확장 가능 |
| **보안 및 통제** | 정해진 API 엔드포인트 샌드박스 내부만 수행되어 **매우 안전** | 터미널 명령을 직접 다루므로 유연하지만 **주의 필요** |
| **추천 활용처** | 다수가 사용하는 웹 서비스, 서버 환경, 권한 제어가 필요한 툴 연동 | 단독 개발자 환경, 빠른 프로토타이핑, CI/CD CLI 작업 자동화 |

---

## 5. React Front 핵심 파일: [Chat.tsx](file:///c:/aiproject/mcpExample/frontend/src/components/Chat.tsx)

프론트엔드 대화형 대시보드 UI를 담당하는 단일 종합 컴포넌트입니다.

* **주요 상태 관리 (State)**:
  * `messages`: 사용자 및 비서 메시지, 실행 플랜, 단계별 도구 실행 로그, 사용된 LLM 모델명을 저장.
  * `tools`: 백엔드의 `GET /tools` 호출로 받아온 MCP 도구 6개의 명세 목록.
  * `activeTab`: 사이드바의 '대화 모드'와 'MCP 스펙' 탭 전환.
* **주요 기능**:
  * **MCP 도구 자동 동기화**: 컴포넌트 마운트 시 `/tools`를 호출하여 가용 툴 스펙 동기화.
  * **빠른 질의 칩 (Quick Prompts)**: "내 레포 목록 조회", "README.md 파일 수정", "최근 커밋 확인", "깃허브 반영해줘" 등 버튼 클릭 시 자동 실행.
  * **투명한 에이전트 추적 UI**: 에이전트가 생성한 실행 계획(Plan), 도구별 파라미터 및 실행 결과 로그(Logs), 그리고 실제 응답을 처리한 Planner/Synthesizer LLM 모델명을 뱃지 형태로 표기.

---

## 6. 시스템에 대한 한 줄 요약
> `mcpExample` 프로젝트는 **React 프론트엔드**에서 입력한 자연어 요청을 **FastAPI 백엔드**가 전달받아 **LangChain 3단계 Fallback AI(Gemini ➔ Groq ➔ Ollama)**를 통해 **MCP 도구 실행 계획**을 세우고, 깃허브 작업 및 로컬 Git 푸시를 자동 수행한 뒤 깔끔한 한국어 보고서를 전달하는 **차세대 AI 에이전트 시스템**입니다.

---

## 7. Git 커밋 메시지 컨벤션 규칙 (Conventional Commits)

본 프로젝트에서는 협업의 효율성을 극대화하고 커밋 히스토리를 명확하게 관리하기 위해 **Conventional Commits** 표준을 준수합니다. GitHub, GitLab 등 현대적인 협업 플랫폼에서 가장 널리 활용되는 규칙을 정리하였습니다.

### 커밋 메시지 기본 구조
```text
<타입>: <설명>
```

### 주요 커밋 타입 및 예시

| 타입 | 의미 | 예시 |
| :--- | :--- | :--- |
| **feat** | 새로운 기능 추가 | `feat: 회원가입 API 추가` |
| **fix** | 버그 수정 | `fix: 로그인 오류 수정` |
| **docs** | 문서 수정 | `docs: README 설치 방법 추가` |
| **style** | 코드 스타일 변경 (기능 변화 없음) | `style: 들여쓰기 및 공백 정리` |
| **refactor** | 리팩토링 (기능 변화 없음) | `refactor: MemberService 코드 개선` |
| **test** | 테스트 코드 추가/수정 | `test: MemberService 단위 테스트 추가` |
| **chore** | 빌드, 설정, 패키지 관리 등 | `chore: Gradle 의존성 업데이트` |
| **build** | 빌드 시스템 변경 | `build: Dockerfile 수정` |
| **ci** | CI/CD 설정 변경 | `ci: GitHub Actions 워크플로 수정` |
| **perf** | 성능 개선 | `perf: Redis 캐시 적용` |
| **revert** | 이전 커밋 되돌리기 | `revert: feat: JWT 로그인 추가` |
| **merge** | 브랜치 병합 | `merge: develop 브랜치를 main으로 병합` |

### 작성 시 권장사항
1. **제목은 명확하고 간결하게**: 변경된 핵심 내용을 한눈에 알 수 있게 50자 내외로 작성합니다.
2. **명확한 타입 구분**: 기능 추가는 `feat`, 단순 수정/보완은 `fix`/`refactor` 등으로 명확히 구분하여 히스토리를 추적하기 쉽게 합니다.
