import re

def remove_ansi_escape_sequences(text):
    try:
        ansi_escape_1 = re.compile(r'\^\[\[([0-9]+)(;[0-9]+)*[mG]')
        ansi_escape_2 = re.compile(r'\x1B[@-_][0-?]*[ -/]*[@-~]')
        message = re.sub(r'\x1b\[[0-9;]*[mK]|\x1b\(B', '', ansi_escape_1.sub('', text))
        cleaned_message = ansi_escape_2.sub('', message)
    except Exception:
        cleaned_message = text
    return cleaned_message

def extract_json_content(text):
    """
    增强版：确保永远返回一个 eval 可解析的字符串
    """
    pattern = r"```json(.*?)```"
    match = re.search(pattern, text, re.DOTALL)
    
    if match:
        return match.group(1).strip().replace('\n','')
    
    # 如果没找到 json 块，尝试寻找括号形式的元组内容
    tuple_pattern = r"(\((?:True|False),\s*.*?\))"
    tuple_match = re.search(tuple_pattern, text, re.DOTALL)
    if tuple_match:
        return tuple_match.group(1)

    # 兜底：返回一个标准的失败元组格式，防止 eval 报错
    return "(False, 'LLM failed to provide structured JSON response.')"
