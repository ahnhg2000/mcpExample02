import os
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
from langgraph.types import Command

from routers.report_graph import report_graph, DOWNLOAD_DIR

router = APIRouter(prefix="/api/reports", tags=["GitHub PDF Report Agent"])

class ReportStartRequest(BaseModel):
    message: str
    thread_id: Optional[str] = "default_session"

class ReportResumeRequest(BaseModel):
    thread_id: str
    action: str # "approve" | "edit"
    feedback: Optional[str] = ""

@router.post("/start")
async def start_report_flow(req: ReportStartRequest):
    """
    1. GitHub 보고서 생성 그래프 실행 엔드포인트:
    입력된 메시지를 기반으로 조건을 검증하고 데이터 수집, 초안 작성 또는 역질문/HITL 대기 상태로 이행합니다.
    """
    thread_id = req.thread_id or "default_session"
    config = {"configurable": {"thread_id": thread_id}}

    # 초기 입력 State
    initial_state = {
        "messages": [{"role": "user", "content": req.message}]
    }

    try:
        # 비동기 그래프 실행
        async for event in report_graph.astream(initial_state, config=config):
            pass # 이벤트 스트리밍 처리

        # 현재 실행 후의 그래프 상태 확인
        current_state = await report_graph.aget_state(config)

        # 1. HITL 중단(interrupt) 발생 여부 체크
        if current_state.tasks and any(t.interrupts for t in current_state.tasks):
            interrupt_data = current_state.tasks[0].interrupts[0].value
            return {
                "status": "hitl_required",
                "thread_id": thread_id,
                "message": interrupt_data.get("message"),
                "draft_report": interrupt_data.get("draft_report")
            }

        # 2. 추가 정보 역질문(ask_clarification) 발생 시
        state_values = current_state.values
        if not state_values.get("is_sufficient") and state_values.get("clarification_message"):
            return {
                "status": "need_clarification",
                "thread_id": thread_id,
                "message": state_values.get("clarification_message")
            }

        # 3. 정상 완결 시 다운로드 파일 정보 반환
        return {
            "status": "completed",
            "thread_id": thread_id,
            "pdf_path": state_values.get("pdf_path"),
            "file_id": state_values.get("file_id"),
            "messages": state_values.get("messages")
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"보고서 생성 프로세스 실행 중 오류 발생: {str(e)}")

@router.post("/resume")
async def resume_report_flow(req: ReportResumeRequest):
    """
    2. HITL (Human-in-the-Loop) 재개 엔드포인트:
    사용자가 UI에서 [승인] 또는 [수정 요청] 입력을 전달하면 중단되었던 LangGraph 그래프를 다시 재개합니다.
    """
    config = {"configurable": {"thread_id": req.thread_id}}

    try:
        # Command(resume=...)로 그래프 재개
        resume_payload = {
            "action": req.action,
            "feedback": req.feedback
        }

        async for event in report_graph.astream(Command(resume=resume_payload), config=config):
            pass

        current_state = await report_graph.aget_state(config)

        # 1. 또다시 피드백 수정 후 HITL 중단 발생 시 (Loop 구조)
        if current_state.tasks and any(t.interrupts for t in current_state.tasks):
            interrupt_data = current_state.tasks[0].interrupts[0].value
            return {
                "status": "hitl_required",
                "thread_id": req.thread_id,
                "message": interrupt_data.get("message"),
                "draft_report": interrupt_data.get("draft_report")
            }

        state_values = current_state.values
        return {
            "status": "completed",
            "thread_id": req.thread_id,
            "pdf_path": state_values.get("pdf_path"),
            "file_id": state_values.get("file_id"),
            "download_url": f"/api/reports/download/{state_values.get('file_id')}"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"HITL 피드백 처리 중 오류 발생: {str(e)}")

@router.get("/download/{file_id}")
async def download_report_pdf(file_id: str):
    """
    3. PDF 보고서 파일 다운로드 엔드포인트
    """
    pdf_filename = f"report_{file_id}.pdf"
    file_path = os.path.join(DOWNLOAD_DIR, pdf_filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="요청하신 PDF 보고서 파일을 찾을 수 없습니다.")

    return FileResponse(
        path=file_path,
        media_type="application/pdf",
        filename=pdf_filename
    )
