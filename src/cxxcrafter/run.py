import os
import sys
import shutil
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
    from src.cxxcrafter.cli import CXXCrafter
except ImportError as e:
    print(f"❌ [Error] Path configuration failed: {e}")
    sys.exit(1)

def update_yaml_metadata(yaml_path, project_name, result):
    with open(yaml_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    for entry in data:
        if entry.get('project') == project_name:
            # `state` records whether this metadata entry has been handled;
            # it is independent from the repair result.  Keep the legacy
            # `fixed_state` field unchanged for compatibility.
            entry['state'] = 'yes'
            entry['fix_result'] = 'Success' if result else 'Failure'
            entry['fix_date'] = datetime.now().strftime('%Y-%m-%d')
            break
    with open(yaml_path, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def cleanup_project_source(project_name, project_path):
    """Remove only the downloaded third-party source after archiving results."""
    project_root = os.path.realpath(os.path.join(root_dir, "process", "project"))
    safe_name = "".join(c for c in project_name if c.isalnum() or c in ('_', '-')).rstrip()
    expected_path = os.path.join(project_root, safe_name)
    actual_path = os.path.realpath(project_path)

    if actual_path != expected_path:
        print(f"⚠️ [Baseline] Skipping cleanup outside managed source path: {actual_path}")
        return
    if os.path.isdir(actual_path):
        shutil.rmtree(actual_path)
        print(f"--- [Baseline] Removed processed third-party source: {actual_path} ---")


def archive_preparation_failure(project_info, reason, start_time):
    """Create the required archive when a project fails before CXXCrafter starts."""
    project_name = project_info['project']
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    archive_dir = os.path.join(root_dir, "archive", project_name)
    patch_dir = os.path.join(archive_dir, "patch")
    result_dir = os.path.join(archive_dir, "repair_result")
    os.makedirs(patch_dir, exist_ok=True)
    os.makedirs(result_dir, exist_ok=True)

    report = (
        f"{'=' * 60}\n"
        f"🏁 FINAL PROJECT REPAIR REPORT: {project_name}\n"
        f"{'-' * 60}\n"
        f"  - [Error Time]: {project_info.get('error_time', 'N/A')}\n"
        f"  - [Result]: ❌ FAILURE\n"
        f"  - [Metadata State]: yes (processed)\n"
        f"  - [Fix Result]: Failure\n"
        f"  - [Repair Rounds]: 0 (CXXCrafter did not start)\n"
        f"  - [Time Cost]: {(datetime.now().timestamp() - start_time) / 60:.2f} minutes\n"
        f"  - [Input Tokens]: N/A (CXXCrafter did not start)\n"
        f"  - [Output Tokens]: N/A (CXXCrafter did not start)\n"
        f"  - [Files Change]: 0\n"
        f"  - [Lines Change]: 0\n"
        f"  - [Failure Reason]: {reason}\n"
        f"{'=' * 60}\n"
    )
    report_path = os.path.join(result_dir, f"{project_name}_fix_result_{timestamp}.txt")
    patch_path = os.path.join(patch_dir, f"{project_name}_fix_{timestamp}.patch")
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    with open(patch_path, 'w', encoding='utf-8') as f:
        f.write("# CXXCrafter did not start; no Dockerfile patch is available.\n")
    print(f"--- [Baseline] Saved preparation failure report: {report_path} ---")


def build_one_repo(project_info, yaml_path):
    project_name = project_info['project']
    start_time = datetime.now().timestamp()
    actual_repo_path = None
    cxxcrafter = None
    safe_name = "".join(c for c in project_name if c.isalnum() or c in ('_', '-')).rstrip()
    managed_repo_path = os.path.join(root_dir, "process", "project", safe_name)

    try:
        oss_fuzz_repo_path = os.path.join(root_dir, "oss-fuzz")
        if not os.path.exists(oss_fuzz_repo_path):
            print(f"--- [Baseline] oss-fuzz not found. Downloading to {oss_fuzz_repo_path} ---")
            download_github_repo("oss-fuzz", oss_fuzz_repo_path)

        print(f"--- [Baseline] Locking OSS-Fuzz SHA: {project_info['oss-fuzz_sha']} ---")
        checkout_oss_fuzz_commit(project_info['oss-fuzz_sha'])

        suggested_repo_path = managed_repo_path
        print(f"--- [Baseline] Ensuring Source Code for {project_name} ---")
        download_res = download_github_repo(
            project_name=project_name,
            target_dir=suggested_repo_path,
            repo_url=project_info.get('software_repo_url')
        )
        if download_res['status'] == 'error':
            raise RuntimeError(f"Download failed: {download_res.get('message')}")

        actual_repo_path = download_res.get('path', suggested_repo_path)
        print(f"--- [Baseline] Locking Software SHA: {project_info['software_sha']} in {actual_repo_path} ---")
        checkout_project_commit(actual_repo_path, project_info['software_sha'])

        cxxcrafter = CXXCrafter(actual_repo_path, project_info=project_info, oss_fuzz_root_path=oss_fuzz_repo_path)
        _, flag_success = cxxcrafter.run()
        update_yaml_metadata(yaml_path, project_name, flag_success)
    except Exception as e:
        print(f"💥 [Baseline] Critical error during execution of {project_name}: {e}")
        update_yaml_metadata(yaml_path, project_name, False)
        if cxxcrafter is None:
            archive_preparation_failure(project_info, str(e), start_time)
    finally:
        cleanup_path = actual_repo_path or managed_repo_path
        if os.path.isdir(cleanup_path):
            cleanup_project_source(project_name, cleanup_path)

def main():
    yaml_path = os.path.join(root_dir, "projects.yaml")
    if not os.path.exists(yaml_path):
        return
    with open(yaml_path, 'r', encoding='utf-8') as f:
        projects = yaml.safe_load(f)
    for entry in projects:
        # `state: 'no'` (or absent state in legacy metadata) means this
        # entry has not yet been processed.
        if entry.get('state', 'no') == 'no':
            print(f"\n{'='*60}\n🛠️ [Baseline] Processing: {entry['project']}\n{'='*60}")
            build_one_repo(entry, yaml_path)

if __name__ == "__main__":
    main()
