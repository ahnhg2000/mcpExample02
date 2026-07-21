import os
import json
import glob
from typing import List, Dict, Any

def load_all_mcp_tools() -> List[Dict[str, Any]]:
    """
    루트 디렉토리의 mcp/ 폴더 내에 존재하는 모든 .json 스펙 파일(github.json, slack.json 등)을
    자동 스캔하여 하나의 MCP 도구 카탈로그 리스트로 통합 로드합니다.
    """
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "mcp"))
    json_files = glob.glob(os.path.join(base_dir, "*.json"))
    
    all_tools: List[Dict[str, Any]] = []
    
    for file_path in json_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                tools = json.load(f)
                if isinstance(tools, list):
                    all_tools.extend(tools)
                elif isinstance(tools, dict):
                    all_tools.append(tools)
        except Exception as e:
            print(f"[Warning] MCP 도구 파일({os.path.basename(file_path)}) 로드 실패: {e}")
            
    return all_tools
