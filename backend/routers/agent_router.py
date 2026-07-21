import sys
import os
import json
import re
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# backend 디렉터리를 sys.path에 최우선 등록
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from llm_router import LLMRouter
from mcp_loader import load_all_mcp_tools
from routers.tools_router import call_tool

router = APIRouter(prefix="/agent", tags=["Agent Core"])
llm_router = LLMRouter()


class TaskRequest(BaseModel):
    description: str


def extract_json_array(text: str) -> List[Dict[str, Any]]:
    """
    LLM 응답 텍스트 내에서 JSON 배열(시퀀스 플랜)을 찾아 파싱합니다.
    """
    try:
        match = re.search(r"\[\s*\{.*\}\s*\]", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return json.loads(text.strip())
    except Exception as e:
        print(f"JSON 파싱 실패 원본 텍스트:\n{text}")
        raise ValueError(f"LLM이 반환한 응답에서 유효한 JSON 실행 계획을 생성하지 못했습니다. (에러: {e})")


@router.post("/task")
async def handle_natural_language_task(task: TaskRequest):
    """
    3. 에이전트 코어 엔드포인트: 통합된 GitHub + Slack + 기타 도구 카탈로그를 기반으로
    자연어 작업을 분석하여 실행 계획 수립 및 순차 실행 결과를 리포트합니다.
    """
    description = task.description
    all_tools = load_all_mcp_tools()

    planner_system_prompt = """당신은 사용자의 요청을 분석하고, 아래 제공된 통합 MCP Tools(GitHub, Slack 등)를 활용하여 어떤 순서로 작업을 실행할지 계획하는 전문 에이전트 코디네이터입니다.

[요청 사항]
1. 사용 가능한 도구 목록(JSON)을 자세히 분석하여, 사용자의 명령을 수행하기 위한 최적의 실행 흐름(시퀀스)을 수립하세요.
2. 이전 도구의 실행 결과(예: read_local_file 결과)를 다음 도구(예: send_slack_message)의 입력 인자로 넘겨야 할 경우, arguments 값에 `{{previous_result}}` 또는 `{{read_local_file.outputs.content}}` 와 같은 템플릿 플레이스홀더를 명시하십시오. 백엔드가 이전 실행 결과를 동적으로 요약/치환하여 실행합니다.
3. 결과는 무조건 실행할 순서대로 정렬된 JSON 배열 포맷 하나만 반환해야 합니다. 설명이나 다른 텍스트는 절대 덧붙이지 마십시오.

[출력 포맷 규격]
[
  {"tool": "도구이름", "arguments": {"인자1": "값1"}}
]

[가용한 MCP 도구 리스트]
""" + json.dumps(all_tools, ensure_ascii=False, indent=2)

    planner_user_prompt = f"사용자의 명령: '{description}'\n위 명령을 수행하기 위한 도구 실행 계획 JSON 배열을 반환하십시오."

    try:
        plan_text, planner_model = await llm_router.generate(planner_system_prompt, planner_user_prompt)
        print(f"[Planner Model: {planner_model}] 수립된 계획:\n{plan_text}")
        
        tool_calls = extract_json_array(plan_text)
        
        execution_logs = []
        last_result_text = ""

        for i, call in enumerate(tool_calls):
            tool_name = call.get("tool")
            args = call.get("arguments", {})
            
            # 동적 템플릿 치환 (이전 실행 결과가 있고 인자에 {{...}} 플레이스홀더가 존재할 경우)
            if last_result_text:
                for k, v in list(args.items()):
                    if isinstance(v, str) and ("{{" in v or "previous_result" in v):
                        # 마크다운 래퍼 등 제거하고 내용만 추출
                        clean_result = re.sub(r"```[a-zA-Z]*\n?", "", last_result_text).replace("```", "").strip()
                        clean_result = re.sub(r"^### .*?\n", "", clean_result).strip()

                        # Slack 메시지 전송인 경우 길면 3줄 요약 수행
                        if tool_name in ["send_slack_message", "upload_file_to_slack"] and len(clean_result) > 200:
                            summary_prompt = f"다음 텍스트 내용을 Slack 메시지에 전송하기 위해 핵심 위주로 3~5줄로 깔끔하게 요약해줘:\n\n{clean_result[:2500]}"
                            summary_text, _ = await llm_router.generate(
                                "당신은 요약 전문가입니다. 인사말이나 다른 말 없이 오직 요약된 메시지 본문만 한국어로 반환하세요.",
                                summary_prompt
                            )
                            replacement = summary_text.strip()
                        else:
                            replacement = clean_result

                        # 템플릿 치환
                        if re.search(r"\{\{.*?\}\}", v):
                            args[k] = re.sub(r"\{\{.*?\}\}", replacement, v)
                        else:
                            args[k] = replacement

            print(f"[Step {i+1}] 실행 도구: {tool_name} | 인자: {args}")
            
            tool_response = await call_tool({"name": tool_name, "arguments": args})
            
            is_error = tool_response.get("isError", False)
            content_list = tool_response.get("content", [])
            response_text = content_list[0].get("text", "") if content_list else "결과 없음"
            
            last_result_text = response_text

            execution_logs.append({
                "step": i + 1,
                "tool": tool_name,
                "arguments": args,
                "success": not is_error,
                "result": response_text
            })

            if is_error:
                print(f"[Step {i+1} Error] 실행 에러로 인해 시퀀스가 중단되었습니다.")
                break

        synthesis_system_prompt = """당신은 GitHub & Slack MCP 에이전트의 결과를 사용자에게 종합하여 보고하는 비서입니다.
사용자의 원래 명령과 실행된 도구들의 단계별 상세 실행 로그를 토대로, 어떤 작업이 수행되었는지 최종 결과를 한국어로 정중하게 설명해 주십시오. 
만약 실행 중 실패한 단계가 있다면 그 원인을 기술 규격에 맞게 친절히 진단해 주십시오."""

        synthesis_user_prompt = f"""[사용자 명령]
{description}

[도구 실행 기록 로그]
{json.dumps(execution_logs, ensure_ascii=False, indent=2)}

위 실행 내역을 기반으로 최종 결과를 리포트 양식으로 간결하고 전문적인 한국어로 작성해 주십시오."""

        final_answer, synthesizer_model = await llm_router.generate(synthesis_system_prompt, synthesis_user_prompt)

        return {
            "status": "success",
            "plan": tool_calls,
            "execution_logs": execution_logs,
            "result": final_answer,
            "planner_model": planner_model,
            "synthesizer_model": synthesizer_model
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"태스크 수행 중 오류가 발생했습니다. (원인: {str(e)})"
        )
