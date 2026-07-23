import os
import uuid
import json
from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt

from llm_router import LLMRouter
from tools.github_tools import get_commit_history, get_pull_requests
from utils.pdf_compiler import markdown_to_pdf

llm_router = LLMRouter()

# Download PDF 저장 경로
DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ----------------------------------------------------
# 1. State 스키마 정의
# ----------------------------------------------------
class ReportState(TypedDict):
    messages: List[Dict[str, Any]]
    repo_name: Optional[str]
    branch: Optional[str]
    date_range: Optional[str]
    report_focus: Optional[str]
    is_sufficient: bool
    github_data: Optional[Dict[str, Any]]
    draft_report: Optional[str]
    user_feedback: Optional[str]
    action: Optional[str] # "approve" | "edit"
    pdf_path: Optional[str]
    file_id: Optional[str]
    clarification_message: Optional[str]

# ----------------------------------------------------
# 2. 8개 노드 함수 구현
# ----------------------------------------------------

async def node_check_conditions(state: ReportState) -> Dict[str, Any]:
    """1. 조건 검증 노드 (Validator)"""
    user_input = ""
    for msg in reversed(state.get("messages", [])):
        if msg.get("role") == "user":
            user_input = msg.get("content", "")
            break

    system_prompt = """당신은 사용자의 요청에서 GitHub 보고서 생성을 위한 필수 조건 3가지를 파싱하고 검증하는 분석기입니다.
[필수 조건]
1. repo_name: 리포지토리 이름 (예: "owner/repo" 또는 "mcpExample02")
2. date_range: 조회 기간 (예: "최근 7일", "v1.0 이후", "2026-07-01 ~ 2026-07-23")
3. report_focus: 보고서 작성 관점/유형 (예: "개발자용 상세 Diff", "PM용 주요 기능 추가 중심", "일반 요약")

[응답 규칙]
- 세 가지 항목이 유저 입력이나 이전 상태에서 모두 확인되면 is_sufficient: true
- 하나라도 명확히 파악되지 않으면 is_sufficient: false
- 결과는 아래 JSON 형식으로만 답하십시오:
{
  "repo_name": "파싱값 또는 null",
  "branch": "파싱값 또는 main",
  "date_range": "파싱값 또는 null",
  "report_focus": "파싱값 또는 null",
  "is_sufficient": true 또는 false
}
"""
    curr_repo = state.get("repo_name")
    curr_date = state.get("date_range")
    curr_focus = state.get("report_focus")

    user_prompt = f"""현재 상태:
- repo_name: {curr_repo}
- date_range: {curr_date}
- report_focus: {curr_focus}

새로운 메시지: "{user_input}"
필수 조건 파싱 및 is_sufficient 판별 결과를 JSON으로 반환하세요."""

    res_text, _ = await llm_router.generate(system_prompt, user_prompt)
    
    try:
        data = json.loads(res_text[res_text.find("{"):res_text.rfind("}")+1])
        return {
            "repo_name": data.get("repo_name") or curr_repo,
            "branch": data.get("branch") or state.get("branch", "main"),
            "date_range": data.get("date_range") or curr_date,
            "report_focus": data.get("report_focus") or curr_focus,
            "is_sufficient": data.get("is_sufficient", False)
        }
    except Exception:
        # 파싱 에러 발생 시 기본 파라미터 적용 여부 판단
        repo = curr_repo or ("mcpExample02" if "mcp" in user_input.lower() else None)
        date = curr_date or ("최근 7일" if "최근" in user_input else None)
        focus = curr_focus or ("주요 기능 변경 중심" if "기능" in user_input else None)
        sufficient = bool(repo and date and focus)
        return {
            "repo_name": repo,
            "date_range": date,
            "report_focus": focus,
            "is_sufficient": sufficient
        }

async def node_ask_clarification(state: ReportState) -> Dict[str, Any]:
    """2. 추가 질문 노드 (Conversational Agent)"""
    missing = []
    if not state.get("repo_name"):
        missing.append("대상 GitHub 리포지토리명 (예: owner/repo 또는 mcpExample02)")
    if not state.get("date_range"):
        missing.append("조회 기간 (예: 최근 7일, v1.0 이후)")
    if not state.get("report_focus"):
        missing.append("보고서 관점 (예: 개발자용 기술 상세 / PM용 주요 기능 요약)")

    msg = f"대표님, 정확하고 깔끔한 보고서 생성을 위해 아래 정보가 필요합니다:\n\n"
    for idx, item in enumerate(missing, 1):
        msg += f"{idx}. **{item}**\n"
    msg += "\n위 내용을 편하게 알려주시면 바로 보고서를 수집하고 작성해 드리겠습니다!"

    messages = state.get("messages", [])
    messages.append({"role": "assistant", "content": msg, "type": "clarification"})
    return {"messages": messages, "clarification_message": msg}

async def node_fetch_github_data(state: ReportState) -> Dict[str, Any]:
    """3. GitHub MCP 데이터 수집 노드 (GitHub MCP Tool)"""
    repo = state.get("repo_name", "mcpExample02")
    branch = state.get("branch", "main")
    date_range = state.get("date_range", "최근 7일")

    print(f"[Fetch GitHub Data] repo: {repo}, branch: {branch}, date: {date_range}")

    # GitHub MCP 도구 호출
    commits_res = await get_commit_history(repo=repo, branch=branch, per_page=15)
    prs_res = await get_pull_requests(repo=repo, state="closed", per_page=10)

    return {
        "github_data": {
            "commits": commits_res,
            "pull_requests": prs_res,
            "query_info": {
                "repo": repo,
                "branch": branch,
                "date_range": date_range
            }
        }
    }

async def node_generate_draft_text(state: ReportState) -> Dict[str, Any]:
    """4. 마크다운 보고서 초안 작성 노드 (Writer Agent)"""
    gh_data = state.get("github_data", {})
    focus = state.get("report_focus", "주요 기능 변경 중심")
    repo = state.get("repo_name", "mcpExample02")
    date_range = state.get("date_range", "최근 7일")

    system_prompt = """당신은 GitHub 커밋 및 PR 변경 이력을 바탕으로 전문적이고 깔끔한 마크다운 보고서를 작성하는 서기 에이전트입니다.
[보고서 양식 가이드]
1. 제목 (# GitHub 변경사항 반영 보고서)
2. 개요 및 요약 (## 1. Executive Summary)
3. 주요 기능 및 버그 수정 내역 (## 2. 주요 변경 사항 (PR & Commit 단위))
4. 영향을 받는 파일 및 모듈 (## 3. 주요 수정 모듈)
5. 향후 점검 항목 (## 4. 종합 의견)

문장은 '대표님'께 전달하는 정중한 한국어로 작성하며, 마크다운 표준 규격을 준수하세요.
"""
    user_prompt = f"""[보고서 조건]
- 리포지토리: {repo}
- 기간: {date_range}
- 보고서 관점: {focus}

[수집된 GitHub RAW 데이터]
{json.dumps(gh_data, ensure_ascii=False, indent=2)[:3500]}

위 데이터를 바탕으로 깔끔한 마크다운 규격의 보고서 초안을 작성하세요."""

    draft, _ = await llm_router.generate(system_prompt, user_prompt)
    return {"draft_report": draft}

async def node_human_review_hitl(state: ReportState) -> Dict[str, Any]:
    """5. Human-in-the-Loop 중단 노드 (HITL Gatekeeper)"""
    # interrupt() 호출로 사용자 검토 대기
    hitl_input = interrupt({
        "type": "human_review",
        "message": "작성된 마크다운 보고서 초안을 검토해 주세요. [승인] 또는 [수정 요청]을 전달하실 수 있습니다.",
        "draft_report": state.get("draft_report")
    })
    
    # resume 데이터 수신 ("action": "approve" | "edit", "feedback": "...")
    action = hitl_input.get("action", "approve")
    feedback = hitl_input.get("feedback", "")
    
    return {
        "action": action,
        "user_feedback": feedback
    }

async def node_refine_draft_text(state: ReportState) -> Dict[str, Any]:
    """6. 초안 수정 노드 (Editor Agent)"""
    curr_draft = state.get("draft_report", "")
    feedback = state.get("user_feedback", "")

    system_prompt = """당신은 기존 마크다운 보고서에 대해 사용자의 피드백을 반영하여 내용을 다듬고 완성도를 높이는 편집 에이전트입니다.
제공된 피드백의 요구사항을 충실히 반영하되 전체 보고서의 구조와 정갈함을 유지하세요."""

    user_prompt = f"""[기존 마크다운 보고서]
{curr_draft}

[사용자 수정 요청 (Human Feedback)]
"{feedback}"

위 수정 요청을 완벽히 반영한 최종 마크다운 보고서를 작성하세요."""

    refined_draft, _ = await llm_router.generate(system_prompt, user_prompt)
    return {"draft_report": refined_draft}

async def node_compile_pdf(state: ReportState) -> Dict[str, Any]:
    """7. PDF 컴파일 노드 (PDF Compiler Tool)"""
    draft = state.get("draft_report", "# 보고서 내용 없음")
    file_id = str(uuid.uuid4())[:8]
    pdf_filename = f"report_{file_id}.pdf"
    output_path = os.path.join(DOWNLOAD_DIR, pdf_filename)

    # Pure Python fpdf2 변환
    markdown_to_pdf(draft, output_path)

    return {
        "pdf_path": output_path,
        "file_id": file_id
    }

async def node_provide_download(state: ReportState) -> Dict[str, Any]:
    """8. 다운로드 제공 노드 (Notifier Agent)"""
    file_id = state.get("file_id", "unknown")
    download_url = f"/api/reports/download/{file_id}"
    
    msg = f"대표님, 요청하신 GitHub 보고서 PDF 생성이 완료되었습니다!\n아래 다운로드 버튼을 클릭하여 PDF 파일(`report_{file_id}.pdf`)을 받으실 수 있습니다."
    
    messages = state.get("messages", [])
    messages.append({
        "role": "assistant",
        "content": msg,
        "type": "download_chip",
        "download_url": download_url,
        "file_id": file_id
    })

    return {"messages": messages}

# ----------------------------------------------------
# 3. 라우팅 에지 조건 정의
# ----------------------------------------------------

def route_after_check(state: ReportState) -> str:
    if state.get("is_sufficient"):
        return "fetch_github_data"
    return "ask_clarification"

def route_after_hitl(state: ReportState) -> str:
    if state.get("action") == "edit":
        return "refine_draft_text"
    return "compile_pdf"

# ----------------------------------------------------
# 4. 그래프 조립 및 컴파일
# ----------------------------------------------------

builder = StateGraph(ReportState)

# 노드 추가
builder.add_node("check_conditions", node_check_conditions)
builder.add_node("ask_clarification", node_ask_clarification)
builder.add_node("fetch_github_data", node_fetch_github_data)
builder.add_node("generate_draft_text", node_generate_draft_text)
builder.add_node("human_review_hitl", node_human_review_hitl)
builder.add_node("refine_draft_text", node_refine_draft_text)
builder.add_node("compile_pdf", node_compile_pdf)
builder.add_node("provide_download", node_provide_download)

# 에지 구성
builder.add_edge(START, "check_conditions")
builder.add_conditional_edges("check_conditions", route_after_check, {
    "ask_clarification": "ask_clarification",
    "fetch_github_data": "fetch_github_data"
})
builder.add_edge("ask_clarification", END)

builder.add_edge("fetch_github_data", "generate_draft_text")
builder.add_edge("generate_draft_text", "human_review_hitl")

builder.add_conditional_edges("human_review_hitl", route_after_hitl, {
    "refine_draft_text": "refine_draft_text",
    "compile_pdf": "compile_pdf"
})
builder.add_edge("refine_draft_text", "human_review_hitl")

builder.add_edge("compile_pdf", "provide_download")
builder.add_edge("provide_download", END)

# 체크포인터 (인메모리 세션 저장)
checkpointer = MemorySaver()

# 그래프 컴파일 (HITL 세션 추적 준비)
report_graph = builder.compile(checkpointer=checkpointer)
