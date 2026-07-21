from typing import Dict, Any
from fastapi import APIRouter, HTTPException
from mcp_loader import load_all_mcp_tools
from tools import execute_tool
from github import GithubException

router = APIRouter(prefix="", tags=["MCP Tools"])


@router.get("/tools")
async def list_tools():
    """
    1. MCP 표준 규격 엔드포인트: mcp/ 폴더의 모든 스펙 파일(github.json, slack.json 등)을 자동 로드하여 반환합니다.
    """
    tools = load_all_mcp_tools()
    return {"tools": tools}


@router.post("/tools/call")
async def call_tool(request: Dict[str, Any]):
    """
    2. MCP 표준 규격 엔드포인트: 도구 이름과 파라미터를 받아 실행한 후 결과를 MCP 규격으로 반환합니다.
    """
    tool_name = request.get("name")
    arguments = request.get("arguments", {})

    if not tool_name:
        raise HTTPException(status_code=400, detail="요청에 도구 이름('name')이 누락되었습니다.")

    try:
        result_text = execute_tool(tool_name, arguments)
        return {
            "content": [
                {
                    "type": "text",
                    "text": result_text
                }
            ]
        }
    except GithubException as ge:
        err_msg = f"GitHub API 호출 실패 (상태코드: {ge.status}): {ge.data.get('message', str(ge))}"
        return {
            "content": [{"type": "text", "text": err_msg}],
            "isError": True
        }
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"도구 실행 에러: {str(e)}"}],
            "isError": True
        }
