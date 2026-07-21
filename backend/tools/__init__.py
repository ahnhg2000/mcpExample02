from typing import Dict, Any
from .github_tools import execute_github_tool
from .slack_tools import execute_slack_tool
from .local_file_tools import execute_local_file_tool

GITHUB_TOOLS = {
    "list_repositories",
    "get_repository_details",
    "read_file_content",
    "create_or_update_file",
    "list_commits",
    "push_all_changes"
}

SLACK_TOOLS = {
    "send_slack_message",
    "list_slack_channels",
    "upload_file_to_slack"
}

LOCAL_FILE_TOOLS = {
    "read_local_file",
    "write_local_file"
}

def execute_tool(tool_name: str, arguments: Dict[str, Any]) -> str:
    """
    모든 MCP 도구들의 통합 실행 디스패처
    """
    if tool_name in GITHUB_TOOLS:
        return execute_github_tool(tool_name, arguments)
    elif tool_name in SLACK_TOOLS:
        return execute_slack_tool(tool_name, arguments)
    elif tool_name in LOCAL_FILE_TOOLS:
        return execute_local_file_tool(tool_name, arguments)
    else:
        raise ValueError(f"정의되지 않았거나 등록되지 않은 MCP 도구입니다: '{tool_name}'")

