import os
from typing import Dict, Any


def get_safe_target_path(project_root: str, rel_path: str) -> str:
    """
    상위 디렉터리 이탈(Directory Traversal) 공격 방지 보안 검증.
    지정한 대상 경로가 프로젝트 루트 내부에 위치하는지 확인합니다.
    """
    # 상대 경로 또는 절대 경로 처리
    if os.path.isabs(rel_path):
        target_path = os.path.abspath(rel_path)
    else:
        target_path = os.path.abspath(os.path.join(project_root, rel_path))

    # 프로젝트 루트와 대상 경로의 공통 경로가 project_root인지 검증
    try:
        common = os.path.commonpath([project_root, target_path])
        if os.path.abspath(common) != project_root:
            raise ValueError(f"허용되지 않은 경로 접근입니다: '{rel_path}' (프로젝트 영역 외부에 접근할 수 없습니다)")
    except ValueError:
        raise ValueError(f"허용되지 않은 경로 접근입니다: '{rel_path}' (프로젝트 영역 외부에 접근할 수 없습니다)")

    return target_path


def execute_local_file_tool(tool_name: str, arguments: Dict[str, Any]) -> str:
    """
    read_local_file 및 write_local_file MCP 도구 실행 함수
    """
    # 보안 강화를 위한 프로젝트 루트 디렉터리 경로 설정 (mcpExample02)
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    # --------------------------------------------------
    # 1. 로컬 파일 읽기 도구 (read_local_file)
    # --------------------------------------------------
    if tool_name == "read_local_file":
        rel_path = arguments.get("file_path")
        if not rel_path:
            raise ValueError("file_path 인자가 누락되었습니다.")

        target_path = get_safe_target_path(project_root, rel_path)

        if not os.path.exists(target_path):
            raise FileNotFoundError(f"존재하지 않는 파일입니다: '{rel_path}'")

        if os.path.isdir(target_path):
            raise IsADirectoryError(f"지정한 경로가 디렉터리입니다: '{rel_path}'")

        with open(target_path, "r", encoding="utf-8") as f:
            content = f.read()

        return f"### 📂 파일 읽기 성공 (`{rel_path}`)\n\n```text\n{content}\n```"

    # --------------------------------------------------
    # 2. 로컬 파일 쓰기 도구 (write_local_file)
    # --------------------------------------------------
    elif tool_name == "write_local_file":
        rel_path = arguments.get("file_path")
        content = arguments.get("content", "")

        if not rel_path:
            raise ValueError("file_path 인자가 누락되었습니다.")

        target_path = get_safe_target_path(project_root, rel_path)

        # 대상 디렉터리가 없으면 자동 생성
        os.makedirs(os.path.dirname(target_path), exist_ok=True)

        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)

        file_size = len(content.encode("utf-8"))
        return f"### 🎉 파일 저장 완료\n- **저장 경로**: `{rel_path}`\n- **파일 크기**: {file_size} 바이트"

    else:
        raise ValueError(f"지원하지 않는 로컬 파일 도구입니다: '{tool_name}'")
