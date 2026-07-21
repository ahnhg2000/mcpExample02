import os
import json
from typing import Dict, Any
from dotenv import load_dotenv

# .env 환경 변수 로드
dotenv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
load_dotenv(dotenv_path=dotenv_path)

try:
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError
    SLACK_SDK_AVAILABLE = True
except ImportError:
    WebClient = None
    SlackApiError = Exception
    SLACK_SDK_AVAILABLE = False

slack_token = os.getenv("SLACK_BOT_TOKEN")
slack_client = WebClient(token=slack_token) if (SLACK_SDK_AVAILABLE and slack_token) else None


def resolve_channel_id(channel_input: str) -> str:
    """
    채널 입력값(채널 ID 또는 채널 이름)을 분석하여 채널 ID 형태로 변환해주는 스마트 헬퍼 함수입니다.
    예: 'C0BJJFA4344' -> 'C0BJJFA4344'
    예: '#mcp-alerts' 또는 'mcp-alerts' -> 'C0BJJFA4344' (슬랙 API 조회 후 매핑)
    """
    if not SLACK_SDK_AVAILABLE:
        raise Exception("slack_sdk 패키지가 설치되지 않았습니다. 'pip install slack_sdk'를 실행해 주십시오.")

    if not slack_client:
        raise Exception("SLACK_BOT_TOKEN이 설정되지 않았습니다. .env 파일에 SLACK_BOT_TOKEN을 설정해 주십시오.")

    clean_input = channel_input.strip()
    
    # 채널 ID 패턴인 경우 (알파벳 대문자 C, G, D로 시작하는 일반적인 Slack ID)
    if clean_input.startswith(("C", "G", "D")) and len(clean_input) >= 8 and not clean_input.startswith("#"):
        return clean_input

    # 채널명인 경우 (# 제거)
    target_name = clean_input.lstrip("#").lower()

    try:
        response = slack_client.conversations_list(types="public_channel,private_channel")
        channels = response.get("channels", [])

        for ch in channels:
            if ch.get("name", "").lower() == target_name:
                return ch["id"]
        
        return clean_input
    except SlackApiError as e:
        print(f"[Warning] Slack 채널 목록 조회 중 에러 발생: {e.response.get('error', str(e))}")
        return clean_input


def execute_slack_tool(tool_name: str, arguments: Dict[str, Any]) -> str:
    """
    Slack 관련 MCP 도구 실행 처리 디스패처
    """
    if not SLACK_SDK_AVAILABLE:
        raise Exception("slack_sdk 라이브러리가 파이썬 환경에 설치되어 있지 않습니다. pip install slack_sdk 를 통해 설치해 주십시오.")

    if not slack_client:
        raise Exception("SLACK_BOT_TOKEN 환경 변수가 설정되지 않았습니다. .env 파일에 SLACK_BOT_TOKEN을 설정해야 Slack 도구를 이용할 수 있습니다.")

    try:
        # 1. 메시지 전송 도구
        if tool_name == "send_slack_message":
            raw_channel = arguments.get("channel") or os.getenv("SLACK_DEFAULT_CHANNEL", "#general")
            message = arguments.get("message")
            blocks = arguments.get("blocks")

            if not message:
                raise Exception("전송할 메시지('message') 내용이 없습니다.")

            channel_id = resolve_channel_id(raw_channel)

            post_kwargs = {
                "channel": channel_id,
                "text": message
            }
            if blocks:
                post_kwargs["blocks"] = blocks

            res = slack_client.chat_postMessage(**post_kwargs)
            return json.dumps({
                "status": "success",
                "message": f"Slack 채널({raw_channel} -> {channel_id})에 성공적으로 메시지를 발송했습니다.",
                "ts": res.get("ts"),
                "channel": res.get("channel")
            }, ensure_ascii=False, indent=2)

        # 2. 채널 목록 조회 도구
        elif tool_name == "list_slack_channels":
            res = slack_client.conversations_list(types="public_channel,private_channel")
            channels = res.get("channels", [])
            
            channel_list = [
                {
                    "id": ch["id"],
                    "name": ch["name"],
                    "is_private": ch.get("is_private", False),
                    "is_member": ch.get("is_member", False),
                    "num_members": ch.get("num_members", 0)
                }
                for ch in channels
            ]
            return json.dumps(channel_list, ensure_ascii=False, indent=2)

        # 3. 파일 업로드 도구
        elif tool_name == "upload_file_to_slack":
            raw_channel = arguments.get("channel") or os.getenv("SLACK_DEFAULT_CHANNEL", "#general")
            file_path = arguments.get("file_path")
            comment = arguments.get("comment", "")

            if not file_path:
                raise Exception("업로드할 파일 경로('file_path')가 누락되었습니다.")

            if not os.path.isabs(file_path):
                project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
                possible_path = os.path.join(project_root, file_path)
                if os.path.exists(possible_path):
                    file_path = possible_path

            if not os.path.exists(file_path):
                raise Exception(f"지정한 파일 경로를 찾을 수 없습니다: '{file_path}'")

            channel_id = resolve_channel_id(raw_channel)

            try:
                res = slack_client.files_upload_v2(
                    channel=channel_id,
                    file=file_path,
                    initial_comment=comment
                )
            except AttributeError:
                res = slack_client.files_upload(
                    channels=channel_id,
                    file=file_path,
                    initial_comment=comment
                )

            return json.dumps({
                "status": "success",
                "message": f"성공적으로 파일('{os.path.basename(file_path)}')을 Slack 채널({raw_channel})에 업로드했습니다.",
                "file_id": res.get("file", {}).get("id") if isinstance(res.get("file"), dict) else "uploaded"
            }, ensure_ascii=False, indent=2)

        else:
            raise ValueError(f"지원하지 않는 Slack 도구입니다: {tool_name}")

    except SlackApiError as e:
        err_msg = e.response.get("error", str(e))
        raise Exception(f"Slack API 호출 실패 (에러 코드: {err_msg})")
