import os
import sys
import yaml
from datetime import datetime

# --- 核心路径修复 ---
current_file_path = os.path.abspath(__file__)
current_dir = os.path.dirname(current_file_path) # src/cxxcrafter
src_dir = os.path.abspath(os.path.join(current_dir, "../")) # src
root_dir = os.path.abspath(os.path.join(src_dir, "../")) # 项目根目录

if src_dir not in sys.path:
    sys.path.insert(0, src_dir)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

try:
    from agent_tools import (
        checkout_oss_fuzz_commit, 
        checkout_project_commit, 
        download_github_repo
    )
    from cxxcrafter.cli import CXXCrafter
except ImportError as e:
    print(f"❌ [Error] Path configuration failed: {e}")
    sys.exit(1)

def update_yaml_metadata(yaml_path, project_name, result):
    with open(yaml_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    for entry in data:
        if entry.get('project') == project_name:
            entry['fixed_state'] = 'yes'
            entry['fix_result'] = 'Success' if result else 'Fail'
            entry['fix_date'] = datetime.now().strftime('%Y-%m-%d')
            break
    with open(yaml_path, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def build_one_repo(project_info, yaml_path):
    project_name = project_info['project']

    # 1. 确保 oss-fuzz 基础设施目录存在
    oss_fuzz_repo_path = os.path.join(root_dir, "oss-fuzz")
    if not os.path.exists(oss_fuzz_repo_path):
        print(f"--- [Baseline] oss-fuzz not found. Downloading to {oss_fuzz_repo_path} ---")
        # 使用工具下载 oss-fuzz
        download_github_repo("oss-fuzz", oss_fuzz_repo_path)

    # 锁定基础设施版本
    print(f"--- [Baseline] Locking OSS-Fuzz SHA: {project_info['oss-fuzz_sha']} ---")
    checkout_oss_fuzz_commit(project_info['oss-fuzz_sha'])

    # 2. 准备第三方软件源码
    suggested_repo_path = os.path.join(root_dir, "process", "project", project_name)
    print(f"--- [Baseline] Ensuring Source Code for {project_name} ---")

    # 调用下载工具并捕获返回结果
    download_res = download_github_repo(
        project_name=project_name,
        target_dir=suggested_repo_path,
        repo_url=project_info.get('software_repo_url')
    )

    if download_res['status'] == 'error':
        print(f"❌ [Baseline] Download failed: {download_res.get('message')}")
        update_yaml_metadata(yaml_path, project_name, False)
        return

    # 【核心修复】：必须使用工具实际返回的 'path'，防止重定向导致找不到目录
    actual_repo_path = download_res.get('path', suggested_repo_path)

    # 3. 在实际路径中锁定软件版本
    print(f"--- [Baseline] Locking Software SHA: {project_info['software_sha']} in {actual_repo_path} ---")
    checkout_project_commit(actual_repo_path, project_info['software_sha'])

    # 4. 启动 CXXCrafter 修复逻辑
    try:
        # 使用 verified 的 actual_repo_path 实例化
        cxxcrafter = CXXCrafter(actual_repo_path, project_info=project_info, oss_fuzz_root_path=oss_fuzz_repo_path)
        _, flag_success = cxxcrafter.run()

        # 更新元数据
        update_yaml_metadata(yaml_path, project_name, flag_success)

    except Exception as e:
        # 记录详细错误，防止主循环崩溃
        print(f"💥 [Baseline] Critical error during execution of {project_name}: {e}")
        update_yaml_metadata(yaml_path, project_name, False)

def main():
    yaml_path = os.path.join(root_dir, "projects.yaml")
    if not os.path.exists(yaml_path):
        return
    with open(yaml_path, 'r', encoding='utf-8') as f:
        projects = yaml.safe_load(f)
    for entry in projects:
        if entry.get('fixed_state', 'no') == 'no':
            print(f"\n{'='*60}\n🛠️ [Baseline] Processing: {entry['project']}\n{'='*60}")
            build_one_repo(entry, yaml_path)

if __name__ == "__main__":
    main()
