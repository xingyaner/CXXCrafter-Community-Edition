import os
import re
import sys
import shutil
import requests
import subprocess
import yaml
from datetime import datetime
from typing import Dict, List, Tuple, Optional

# 仅保留物理环境相关的路径常量
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))


def download_github_repo(project_name: str, target_dir: str, repo_url: Optional[str] = None) -> Dict[str, str]:
    """
    【路径安全+全量克隆版】下载仓库工具
    1. 强制路径锁定：第三方库仅允许存放在 process/project/ 下。
    2. 全量克隆：移除 --depth=1，确保 checkout sha 100% 成功。
    3. 缓冲区优化：解决大仓库 RPC 错误。
    """
    import json
    import time
    import subprocess
    import os
    import shutil

    # --- 核心逻辑：路径强制重定向 ---
    current_work_dir = os.getcwd()
    if project_name == "oss-fuzz":
        # oss-fuzz 保持原样（通常在 ./oss-fuzz）
        final_target_dir = os.path.abspath(target_dir)
    else:
        # 强制所有其他项目进入 process/project/ 目录
        safe_name = "".join(c for c in project_name if c.isalnum() or c in ('_', '-')).rstrip()
        final_target_dir = os.path.abspath(os.path.join(current_work_dir, "process", "project", safe_name))
        
        if os.path.abspath(target_dir) != final_target_dir:
            print(f"--- Path Security Enforcement: Redirecting download from {target_dir} to {final_target_dir} ---")

    print(f"--- Tool: download_github_repo called for '{project_name}' ---")

    # --- 1. 预检查逻辑：确保 Git 仓库完整性 ---
    if os.path.isdir(final_target_dir) and os.path.exists(os.path.join(final_target_dir, ".git")):
        if project_name == "oss-fuzz":
            print(f"--- oss-fuzz exists, pulling latest... ---")
            try:
                subprocess.run(["git", "pull"], cwd=final_target_dir, check=True, capture_output=True)
                return {'status': 'success', 'path': final_target_dir, 'message': 'oss-fuzz updated.'}
            except:
                return {'status': 'success', 'path': final_target_dir, 'message': 'oss-fuzz update failed, using local.'}
        else:
            print(f"--- Repo '{project_name}' exists and is a valid git repo. Skipping download. ---")
            return {'status': 'success', 'path': final_target_dir, 'message': 'Repository already exists.'}

    # 清理非 Git 目录残余
    if os.path.isdir(final_target_dir):
        shutil.rmtree(final_target_dir)
    os.makedirs(os.path.dirname(final_target_dir), exist_ok=True)

    # --- 2. 确定 Repo URL ---
    final_repo_url = repo_url if repo_url and repo_url.strip() else None
    if not final_repo_url:
        if project_name == "oss-fuzz":
            final_repo_url = "https://github.com/google/oss-fuzz.git"
        else:
            try:
                search_cmd = ["gh", "search", "repos", project_name, "--sort", "stars", "--limit", "1", "--json", "fullName"]
                result = subprocess.run(search_cmd, capture_output=True, text=True, check=True, encoding='utf-8')
                parsed = json.loads(result.stdout.strip())
                if parsed:
                    final_repo_url = f"https://github.com/{parsed[0]['fullName']}.git"
                else:
                    return {'status': 'error', 'message': f"Repo not found for {project_name}"}
            except Exception as e:
                return {'status': 'error', 'message': f"Search failed: {e}"}

    # --- 3. 配置 Git 缓冲区（解决 TLS/RPC 错误） ---
    subprocess.run(["git", "config", "--global", "http.postBuffer", "524288000"])
    subprocess.run(["git", "config", "--global", "http.lowSpeedLimit", "0"])
    subprocess.run(["git", "config", "--global", "http.lowSpeedTime", "999999"])

    # --- 4. 增强重试克隆逻辑 (注意：此处已移除 --depth=1) ---
    max_retries = 3
    for attempt in range(max_retries):
        print(f"--- Download attempt {attempt + 1}/{max_retries} ---")
        try:
            # 执行全量克隆以支持 SHA 切换
            clone_cmd = ["git", "clone", final_repo_url, final_target_dir]
            result = subprocess.run(clone_cmd, capture_output=True, text=True)
            if result.returncode == 0:
                return {'status': 'success', 'path': final_target_dir, 'message': 'Successfully cloned.'}
            else:
                print(f"--- Attempt {attempt+1} failed: {result.stderr} ---")
        except Exception as e:
            print(f"--- Attempt {attempt+1} exception: {e} ---")
        time.sleep(10 * (attempt + 1))

    return {'status': 'error', 'message': f"Failed to download {project_name} after {max_retries} attempts."}

def checkout_project_commit(project_source_path: str, sha: str) -> Dict[str, str]:
    """
    在目标软件项目的源代码目录中执行 git checkout 命令。
    """
    print(f"--- Tool: checkout_project_commit called for SHA: {sha} in '{project_source_path}' ---")

    if not os.path.isdir(os.path.join(project_source_path, ".git")):
        return {'status': 'error', 'message': f"The directory '{project_source_path}' is not a git repository."}

    original_path = os.getcwd()
    try:
        os.chdir(project_source_path)

        # 确保仓库处于干净状态，避免 checkout 冲突
        subprocess.run(["git", "reset", "--hard", "HEAD"], capture_output=True, text=True, check=True)
        subprocess.run(["git", "clean", "-fdx"], capture_output=True, text=True, check=True)

        command = ["git", "checkout", sha]
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')

        if result.returncode == 0:
            return {'status': 'success', 'message': f"Successfully checked out SHA {sha} in project source."}
        else:
            return {'status': 'error', 'message': f"Git command failed in project source: {result.stderr.strip()}"}
    except Exception as e:
        return {'status': 'error', 'message': f"An unexpected error occurred during project source checkout: {e}"}
    finally:
        os.chdir(original_path)

def checkout_oss_fuzz_commit(sha: str) -> Dict[str, str]:
    """
    [Revised] Executes a git checkout command in the fixed oss-fuzz directory.
    """
    base_path = os.path.abspath(os.path.join(os.path.dirname(__file__)))
    oss_fuzz_path = os.path.join(base_path, "oss-fuzz")
    print(f"--- Tool: checkout_oss_fuzz_commit called for SHA: {sha} in '{oss_fuzz_path}' ---")

    if not os.path.isdir(os.path.join(oss_fuzz_path, ".git")):
        return {'status': 'error', 'message': f"The directory '{oss_fuzz_path}' is not a git repository."}

    original_path = os.getcwd()
    try:
        os.chdir(oss_fuzz_path)
        main_branch = "main" if "main" in subprocess.run(["git", "branch"], capture_output=True, text=True).stdout else "master"
        subprocess.run(["git", "switch", main_branch], capture_output=True, text=True)

        command = ["git", "checkout", sha]
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')

        if result.returncode == 0:
            return {'status': 'success', 'message': f"Successfully checked out SHA {sha}."}
        else:
            return {'status': 'error', 'message': f"Git command failed: {result.stderr.strip()}"}
    except Exception as e:
        return {'status': 'error', 'message': f"An unexpected error occurred during checkout: {e}"}
    finally:
        os.chdir(original_path)


def run_fuzz_build_streaming(
    project_name: str,
    oss_fuzz_path: str,
    sanitizer: str,
    engine: str,
    architecture: str,
    mount_path: Optional[str] = None  # 新增可选参数
) -> dict:
    """
    【增强版】执行 Fuzzing 构建命令。
    如果提供了 mount_path，则使用挂载本地源码的命令格式。
    """
    print(f"--- Tool: run_fuzz_build_streaming (Enhanced) called for project: {project_name} ---")
    if mount_path:
        print(f"--- Build Mode: Source Mount (Path: {mount_path}) ---")
    else:
        print(f"--- Build Mode: Standard Configuration ---")

    LOG_DIR = "fuzz_build_log_file"
    LOG_FILE_PATH = os.path.join(LOG_DIR, "fuzz_build_log.txt")
    os.makedirs(LOG_DIR, exist_ok=True)

    try:
        helper_script_path = os.path.join(oss_fuzz_path, "infra/helper.py")
        
        # 构建基础命令
        command = ["python3.10", helper_script_path, "build_fuzzers"]
        
        # 根据策略调整参数顺序
        # 格式 1 (Config Fix): build_fuzzers --sanitizer ... <project_name>
        # 格式 2 (Source Fix): build_fuzzers <project_name> <source_path> --sanitizer ...
        
        if mount_path:
            # 源码挂载模式：显式指定项目名和路径
            command.append(project_name)
            command.append(mount_path)
        
        # 添加通用参数
        command.extend([
            "--sanitizer", sanitizer, 
            "--engine", engine, 
            "--architecture", architecture
        ])

        # 如果不是挂载模式，项目名通常在最后（或者根据 helper.py 的具体实现，放在中间也可以，但为了保险起见，遵循标准 oss-fuzz 用法）
        # 标准用法通常是: build_fuzzers --args project_name
        if not mount_path:
            command.append(project_name)

        print(f"--- Executing command: {' '.join(command)} ---")

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=oss_fuzz_path,
            encoding='utf-8',
            errors='ignore'
        )

        full_log_content = []
        for line in process.stdout:
            print(line, end='', flush=True)
            full_log_content.append(line)
        
        process.wait()
        return_code = process.returncode
        print("\n--- Fuzzing process finished. ---")

        final_log = "".join(full_log_content)
        
        failure_keywords = [
            "error:", "failed:", "timeout", "timed out", "build failed",
            "no such package", "error loading package", "failed to fetch"
        ]
        
        success_keywords = ["build completed successfully", "successfully built"]
        
        is_truly_successful = True
        
        if return_code != 0:
            is_truly_successful = False
            
        if any(keyword in final_log.lower() for keyword in failure_keywords):
            is_truly_successful = False
            
        if is_truly_successful:
            if not any(keyword in final_log.lower() for keyword in success_keywords):
                if "found 0 targets" in final_log.lower():
                    is_truly_successful = False
        
        # --- 根据判断结果写入文件并返回 ---
        if is_truly_successful:
            content_to_write = "success"
            message = f"Fuzzing build command appears TRULY SUCCESSFUL. Result saved to '{LOG_FILE_PATH}'."
            status = "success"
        else:
            # 如果失败，保存完整的日志
            content_to_write = final_log
            message = f"Fuzzing build command FAILED based on log analysis. Detailed log saved to '{LOG_FILE_PATH}'."
            status = "error"
            
        with open(LOG_FILE_PATH, "w", encoding="utf-8") as f:
            f.write(content_to_write)
            
        print(message)
        return {"status": status, "message": message}

    except Exception as e:
        message = f"An unknown exception occurred: {str(e)}"
        print(message)
        with open(LOG_FILE_PATH, "w", encoding="utf-8") as f:
            f.write(message)
        return {"status": "error", "message": message}


def read_file_content(file_path: str, tail_lines: Optional[int] = None) -> dict:
    """
    【上下文优化版】读取文件内容，并自动进行瘦身以减少 token 数量。
    - 自动剥离常见的许可证头部注释。
    - 对过长的文件进行智能截断（保留开头和结尾）。
    - 接受 tail_lines 参数只读取末尾行。
    """
    print(f"--- Tool: read_file_content (Optimized) called for: {file_path} (tail_lines={tail_lines}) ---")
    
    if not os.path.isfile(file_path):
        return {"status": "error", "message": f"Error: Path '{file_path}' is not a valid file."}
        
    try:
        with open(file_path, "r", encoding="utf-8", errors='ignore') as f:
            lines = f.readlines()

        # 1. 如果指定了 tail_lines，则优先处理
        if tail_lines and isinstance(tail_lines, int) and tail_lines > 0:
            content = "".join(lines[-tail_lines:])
            message = f"Successfully read the last {len(lines[-tail_lines:])} lines from '{file_path}'."
            return {"status": "success", "message": message, "content": content}

        # 2. 自动剥离常见的许可证/版权头部
        # 匹配以 #, /*, // 开头的连续行
        license_header_pattern = re.compile(r"^(#|//|\s*\*).*$", re.MULTILINE)
        content_str = "".join(lines)
        
        # 寻找第一个非注释行
        first_code_line_index = -1
        for i, line in enumerate(lines):
            stripped_line = line.strip()
            if stripped_line and not license_header_pattern.match(line):
                first_code_line_index = i
                break
        
        if first_code_line_index > 5: # 如果头部注释超过5行，就剥离它
            lines = lines[first_code_line_index:]
            print(f"--- Stripped license header ({first_code_line_index} lines) from '{file_path}' ---")

        # 3. 对过长的文件进行智能截断
        MAX_LINES = 400 # 设置一个合理的文件最大行数
        if len(lines) > MAX_LINES:
            head = lines[:MAX_LINES // 2]
            tail = lines[-MAX_LINES // 2:]
            content = "".join(head) + "\n\n... (File content truncated for brevity) ...\n\n" + "".join(tail)
            message = f"File '{file_path}' was too long, content has been truncated."
            print(f"--- Truncated long file '{file_path}' to {MAX_LINES} lines ---")
        else:
            content = "".join(lines)
            message = f"Successfully read the optimized content of '{file_path}'."

        return {"status": "success", "message": message, "content": content}

    except Exception as e:
        return {"status": "error", "message": f"An error occurred while reading file '{file_path}': {str(e)}"}


def force_clean_git_repo(repo_path: str) -> Dict[str, str]:
    print(f"--- Tool: force_clean_git_repo (v2) called for: {repo_path} ---")

    if not os.path.isdir(os.path.join(repo_path, ".git")):
        return {'status': 'error', 'message': f"Directory '{repo_path}' is not a valid Git repository."}

    original_path = os.getcwd()
    try:
        os.chdir(repo_path)

        # 1. First, switch to the main branch. Using -f or --force can force a switch, but resetting first is safer.
        # 2. Force reset to HEAD, which will discard all modifications in the working directory. This is the most critical step.
        subprocess.run(["git", "reset", "--hard", "HEAD"], capture_output=True, text=True, check=True)

        # 3. Now that the workspace is clean, we can safely switch branches.
        main_branch = "main" if "main" in subprocess.run(["git", "branch", "--list"], capture_output=True, text=True).stdout else "master"
        subprocess.run(["git", "switch", main_branch], capture_output=True, text=True, check=True)

        # 4. Remove all untracked files and directories (e.g., build artifacts, logs).
        subprocess.run(["git", "clean", "-fdx"], capture_output=True, text=True, check=True)

        message = f"Successfully force-cleaned the repository '{repo_path}'. All local changes and untracked files have been removed."
        print(message)
        return {'status': 'success', 'message': message}

    except subprocess.CalledProcessError as e:
        message = f"Failed to force-clean repository '{repo_path}': {e.stderr.strip()}"
        print(f"--- ERROR: {message} ---")
        return {'status': 'error', 'message': message}
    except Exception as e:
        message = f"An unknown error occurred while cleaning the repository: {e}"
        print(f"--- ERROR: {message} ---")
        return {'status': 'error', 'message': message}
    finally:
        os.chdir(original_path)


def get_project_paths(project_name: str) -> Dict[str, str]:
    """
    Generates and returns the standard project_config_path and project_source_path based on the project name.
    """
    print(f"--- Tool: get_project_paths called for: {project_name} ---")
    # Ensure paths are always relative to the parent directory of the current script file (i.e., the project root)
    base_path = os.path.abspath(os.path.join(os.path.dirname(__file__)))

    safe_project_name = "".join(c for c in project_name if c.isalnum() or c in ('_', '-')).rstrip()

    config_path = os.path.join(base_path, "oss-fuzz", "projects", safe_project_name)
    source_path = os.path.join(base_path, "process", "project", safe_project_name)

    paths = {
        "project_name": project_name,
        "project_config_path": config_path,
        "project_source_path": source_path,
        "max_depth": 1 # Default to getting 1 level of the file tree
    }
    print(f"--- Generated paths: {paths} ---")
    return paths
