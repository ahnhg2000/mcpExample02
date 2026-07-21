import os
import json
import difflib
import subprocess
from typing import Dict, Any
from dotenv import load_dotenv
from fastapi import HTTPException
from github import Github, GithubException

# .env 환경 변수 로드
dotenv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
load_dotenv(dotenv_path=dotenv_path)

github_token = os.getenv("GITHUB_TOKEN")
if not github_token:
    print("[Warning] GITHUB_TOKEN 환경 변수가 설정되지 않았습니다. GitHub 도구 호출 시 오류가 발생할 수 있습니다.")

github_client = Github(github_token) if github_token else None


def get_user_repo(repo_name: str):
    """
    저장소명을 기반으로 PyGithub Repository 객체를 획득하는 헬퍼 함수.
    'owner/repo' 형태와 일반 'repo' 형태를 모두 지원하며, 404 에러 시 유사한 저장소명으로 오타 보정을 시도합니다.
    """
    if not github_client:
        raise HTTPException(status_code=500, detail="GitHub 클라이언트가 초기화되지 않았습니다. GITHUB_TOKEN을 확인해 주십시오.")
    
    try:
        if "/" in repo_name:
            return github_client.get_repo(repo_name)
        else:
            user = github_client.get_user()
            return user.get_repo(repo_name)
    except GithubException as e:
        if e.status == 404:
            try:
                user = github_client.get_user()
                repos = user.get_repos()
                
                if "/" in repo_name:
                    repo_full_names = [r.full_name for r in repos]
                    matches = difflib.get_close_matches(repo_name, repo_full_names, n=1, cutoff=0.6)
                    if matches:
                        corrected_name = matches[0]
                        print(f"[Fuzzy Match] 저장소명 오타 감지 (full_name): '{repo_name}' -> '{corrected_name}'으로 자동 보정하여 시도합니다.")
                        return github_client.get_repo(corrected_name)
                else:
                    repo_names = [r.name for r in repos]
                    matches = difflib.get_close_matches(repo_name, repo_names, n=1, cutoff=0.6)
                    if matches:
                        corrected_name = matches[0]
                        print(f"[Fuzzy Match] 저장소명 오타 감지 (name): '{repo_name}' -> '{corrected_name}'으로 자동 보정하여 시도합니다.")
                        return user.get_repo(corrected_name)
            except Exception as fuzzy_err:
                print(f"[Fuzzy Match Error] 오타 자동 보정 시도 중 에러 발생: {fuzzy_err}")
                
        raise HTTPException(
            status_code=e.status,
            detail=f"GitHub 저장소 '{repo_name}'를 찾을 수 없거나 접근 권한이 없습니다. (원인: {e.data.get('message', str(e))})"
        )


def execute_github_tool(tool_name: str, arguments: Dict[str, Any]) -> str:
    """
    GitHub 관련 MCP 도구 실행 처리 디스패처
    """
    if tool_name == "list_repositories":
        if not github_client:
            raise Exception("GITHUB_TOKEN이 존재하지 않거나 클라이언트가 초기화되지 않았습니다.")
        repos = github_client.get_user().get_repos()
        repo_list = [{"name": r.name, "full_name": r.full_name, "private": r.private} for r in repos[:10]]
        return json.dumps(repo_list, ensure_ascii=False, indent=2)

    elif tool_name == "get_repository_details":
        repo_name = arguments.get("repo_name")
        repo = get_user_repo(repo_name)
        details = {
            "name": repo.name,
            "full_name": repo.full_name,
            "description": repo.description,
            "stars": repo.stargazers_count,
            "language": repo.language,
            "forks": repo.forks_count,
            "owner": repo.owner.login
        }
        return json.dumps(details, ensure_ascii=False, indent=2)

    elif tool_name == "read_file_content":
        repo_name = arguments.get("repo_name")
        path = arguments.get("path")
        repo = get_user_repo(repo_name)
        file_content = repo.get_contents(path)
        return file_content.decoded_content.decode("utf-8")

    elif tool_name == "create_or_update_file":
        repo_name = arguments.get("repo_name")
        path = arguments.get("path")
        content = arguments.get("content")
        commit_message = arguments.get("commit_message", "Updated via MCP Agent")
        
        repo = get_user_repo(repo_name)
        
        try:
            file_info = repo.get_contents(path)
            res = repo.update_file(path, commit_message, content, file_info.sha)
            return f"성공적으로 '{path}' 파일을 수정(업데이트)했습니다. 커밋 SHA: {res['commit'].sha}"
        except GithubException as ge:
            if ge.status == 404:
                res = repo.create_file(path, commit_message, content)
                return f"성공적으로 '{path}' 파일을 신규 생성했습니다. 커밋 SHA: {res['commit'].sha}"
            else:
                raise ge

    elif tool_name == "list_commits":
        repo_name = arguments.get("repo_name")
        limit = int(arguments.get("limit", 5))
        repo = get_user_repo(repo_name)
        commits = repo.get_commits()
        commit_list = []
        for c in commits[:limit]:
            commit_list.append({
                "sha": c.sha[:8],
                "author": c.commit.author.name,
                "message": c.commit.message,
                "date": c.commit.author.date.isoformat()
            })
        return json.dumps(commit_list, ensure_ascii=False, indent=2)

    elif tool_name == "push_all_changes":
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        
        subprocess.run(["git", "config", "core.quotepath", "false"], cwd=project_root, capture_output=True)
        
        status_res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore"
        )
        
        if status_res.returncode != 0:
            raise Exception(f"git status 실행 실패: {status_res.stderr}")
            
        status_output = status_res.stdout.strip()
        if not status_output:
            return "### ℹ️ 알림\n로컬 저장소에 반영할 변경 사항이 없습니다. 작업 폴더가 이미 최신 상태입니다."
        else:
            lines = status_output.split("\n")
            added_files = []
            modified_files = []
            deleted_files = []
            
            for line in lines:
                if not line.strip():
                    continue
                status_flag = line[:2]
                file_path = line[2:].strip().strip('"')
                
                if "A" in status_flag or "??" in status_flag:
                    added_files.append(file_path)
                elif "M" in status_flag:
                    modified_files.append(file_path)
                elif "D" in status_flag:
                    deleted_files.append(file_path)
            
            commit_message = arguments.get("commit_message")
            if not commit_message:
                summary_parts = []
                if added_files:
                    summary_parts.append(f"Add {', '.join(added_files[:2])}" + ("..." if len(added_files) > 2 else ""))
                if modified_files:
                    summary_parts.append(f"Update {', '.join(modified_files[:2])}" + ("..." if len(modified_files) > 2 else ""))
                if deleted_files:
                    summary_parts.append(f"Delete {', '.join(deleted_files[:2])}" + ("..." if len(deleted_files) > 2 else ""))
                
                commit_message = "style/feat: " + " | ".join(summary_parts) if summary_parts else "Auto-committed by MCP Agent"
            
            add_res = subprocess.run(["git", "add", "."], cwd=project_root, capture_output=True, text=True, encoding="utf-8", errors="ignore")
            if add_res.returncode != 0:
                raise Exception(f"git add 실패: {add_res.stderr}")
            
            commit_res = subprocess.run(["git", "commit", "-m", commit_message], cwd=project_root, capture_output=True, text=True, encoding="utf-8", errors="ignore")
            if commit_res.returncode != 0:
                raise Exception(f"git commit 실패: {commit_res.stderr}")
            
            push_res = subprocess.run(["git", "push"], cwd=project_root, capture_output=True, text=True, encoding="utf-8", errors="ignore")
            if push_res.returncode != 0:
                raise Exception(f"git push 실패: {push_res.stderr}")
            
            sha_res = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=project_root, capture_output=True, text=True)
            commit_sha = sha_res.stdout.strip() if sha_res.returncode == 0 else "N/A"
            
            report = []
            report.append("### 🎉 GitHub 반영 성공 완료 보고서")
            report.append(f"- **커밋 메시지**: `{commit_message}`")
            report.append(f"- **커밋 SHA**: `{commit_sha}`")
            report.append(f"- **대상 브랜치**: `main` (origin)")
            report.append("\n#### 📂 변경된 파일 내역 목록")
            report.append("| 상태 | 파일 경로 |")
            report.append("| :--- | :--- |")
            
            for f in added_files:
                report.append(f"| 🟢 신규 추가 (Added) | `{f}` |")
            for f in modified_files:
                report.append(f"| 🟡 변경 수정 (Modified) | `{f}` |")
            for f in deleted_files:
                report.append(f"| 🔴 삭제 제거 (Deleted) | `{f}` |")
            
            return "\n".join(report)

    else:
        raise ValueError(f"지원하지 않는 GitHub 도구입니다: {tool_name}")
