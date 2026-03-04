import re, os
import logging

def extract_dockerfile_content(text):
    pattern = r"```[dD]ockerfile(.*?)```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    else:
        # 修正：必须抛出 Exception 对象
        raise ValueError("LLM response did not contain a Dockerfile code block.")

def save_dockerfile(project_dir, dockerfile_content):
    if not os.path.exists(project_dir):
        os.makedirs(project_dir, exist_ok=True)
    with open(os.path.join(project_dir, 'Dockerfile'), 'w') as f:
        f.write(dockerfile_content)

def resave_dockerfile(dockerfile_path, dockerfile_content):
    with open(dockerfile_path, 'w') as f:
        f.write(dockerfile_content)
