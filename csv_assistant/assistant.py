import os
import sys
import json
import re
import traceback
from io import StringIO
from contextlib import redirect_stdout

import openai
import pandas as pd
import textwrap
from prompt_toolkit import prompt
import base64

# 生成图片的默认输出目录（当前脚本所在目录）
OUTPUT_DIR = os.path.dirname(__file__) or "."

# 需要预先在环境变量中设置 OPENAI_API_KEY
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("请先在环境变量中设置 OPENAI_API_KEY")
    sys.exit(1)

client = openai.OpenAI(api_key=OPENAI_API_KEY,
                      base_url="https://yunwu.ai/v1")

DEFAULT_MODEL = input("请输入要使用的大模型名称 (例如 gpt-4o): ").strip()


def call_llm(messages, model: str = DEFAULT_MODEL, **kwargs) -> str:
    try:
        response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=kwargs.get("temperature", 0.1),
    )
    except openai.AuthenticationError:
        print(
            "[错误] OpenAI API 鉴权失败：请检查 OPENAI_API_KEY 是否设置正确，"
            "可在 https://platform.openai.com/account/api-keys 查看并重新导出。"
        )
        sys.exit(1)
    except openai.OpenAIError as e:
        print("[错误] 调用 OpenAI 接口时发生异常：", e)
        sys.exit(1)

    return response.choices[0].message.content.strip()


def extract_code(content: str) -> str | None:
    code_match = re.search(r"```python(.*?```)", content, re.S)
    if not code_match:
        code_match = re.search(r"```(.*?```)", content, re.S)
    if not code_match:
        return None
    code_block = code_match.group(1)
    code = re.sub(r"```", "", code_block).strip()
    return code


def execute_python(code: str, exec_globals: dict | None = None):
    """执行 code 并捕获 stdout / traceback"""
    exec_globals = exec_globals or {}
    stdout_buf = StringIO()
    err_trace = None
    try:
        with redirect_stdout(stdout_buf):
            exec(code, exec_globals)
    except Exception:
        err_trace = traceback.format_exc()
    return stdout_buf.getvalue(), err_trace


def system_prompt(df_sample: pd.DataFrame) -> str:
    cols = ", ".join(df_sample.columns)
    sample = textwrap.indent(df_sample.head().to_string(index=False), "    ")
    return textwrap.dedent(f"""
    你是一名资深数据分析师，需要根据用户的自然语言指令，对已经加载到变量 `df` 的 pandas DataFrame 数据进行分析。

    当前 DataFrame 的列包括：{cols}
    前几行示例：
    {sample}

    请严格遵循以下约束：
    1. 不要重新读取 CSV；数据已在变量 `df` 中。\n
    2. 如果需要展示图表，请在代码中保存为 'output1.png'、'output2.png' 等文件，并**务必使用 `print()` 输出关键汇总信息**（例如聚合后的 DataFrame、描述性统计或结论性语句），保证终端有可供阅读的文字结果。\n
    3. 回复仅包含 markdown 代码块，格式示例：```python\n#your code```。\n
    4. 如果用户的问题与 `df` 无关（聊天、编程、知识问答等），请像 ChatGPT 一样自然回答，不要输出代码块。\n
    """)



def ask(question: str, history: list[dict], df: pd.DataFrame, exec_globals: dict, model: str, explain_model: str | None = "gpt-3.5-turbo") -> dict:
    """与大模型单轮对话，返回执行结果并将记录追加到 history。

    返回字段：
        code:  生成的 Python 代码（可能为空）
        stdout: 代码执行输出
        explanation: 生成的中文解释
    """

    # 构建 prompt 消息
    messages = [{"role": "system", "content": system_prompt(df)}]
    for h in history:
        messages += [
            {"role": "user", "content": h["question"]},
            {"role": "assistant", "content": f"```python\n{h['code']}\n```" if h["code"] else ""},
            {"role": "assistant", "content": h["stdout"]},
            {"role": "assistant", "content": h["explanation"]},
        ]
    messages.append({"role": "user", "content": question})

    # 第一次向 LLM 请求
    assistant_reply = call_llm(messages, model)
    code = extract_code(assistant_reply)

    # 若未返回代码，直接当作普通聊天
    if not code:
        result = {"code": "", "stdout": "", "explanation": assistant_reply,"images":[]}
        history.append({**result, "question": question})
        return result

    # 执行前图片快照
    try:
        before_files = {f for f in os.listdir(OUTPUT_DIR) if f.endswith(".png")}
    except FileNotFoundError:
        before_files = set()

    # 若返回代码，则尝试执行并自动纠错
    max_retry = 5
    for _ in range(max_retry + 1):
        stdout, err = execute_python(code, exec_globals)
        if err is None:
            break
        messages.append({"role": "assistant", "content": f"前段代码报错信息:\n{err}"})
        assistant_reply = call_llm(messages, model)
        code = extract_code(assistant_reply) or code
    if err is not None:
        raise RuntimeError(f"代码仍有错误:\n{err}")

    # 执行后图片快照
    try:
        after_files = {f for f in os.listdir(OUTPUT_DIR) if f.endswith(".png")}
    except FileNotFoundError:
        after_files = set()

    new_image_files = list(after_files - before_files)
    images_base64: list[str] = []
    for fname in new_image_files:
        fpath = os.path.join(OUTPUT_DIR, fname)
        try:
            with open(fpath, "rb") as img_f:
                encoded = base64.b64encode(img_f.read()).decode("utf-8")
                images_base64.append(f"data:image/png;base64,{encoded}")
        except Exception as e:
            print(f"读取图片 {fname} 失败: {e}")

    # 生成解释
    explain_prompt = [
        {
            "role": "system",
            "content": (
                "你是一名专业数据分析师。请阅读给出的 Python 代码及其执行输出，"
                "用中文给出详细、通俗的解释，必要时指出图表或数据含义。"
            ),
        },
        {
            "role": "user",
            "content": ("代码:\n```python\n" + code + "\n```\n\n执行输出:\n" + stdout),
        },
    ]
    explanation = call_llm(explain_prompt, explain_model or model)

    result = {"code": code, "stdout": stdout, "explanation": explanation, "images": images_base64}
    history.append({**result, "question": question})
    return result


def main():
    if len(sys.argv) < 2:
        print("不要忘记输入文件路径！请在终端输入: python assistant.py <csv_file_path>")
        sys.exit(1)

    csv_path = sys.argv[1]
    if not os.path.exists(csv_path):
        print(f"文件不存在: {csv_path}")
        sys.exit(1)

    print("正在加载数据...")
    df = pd.read_csv(csv_path)
    print(f"数据加载完成，包含 {df.shape[0]} 行 {df.shape[1]} 列。\n")

    # 选择模型
    model = DEFAULT_MODEL
    if not model:
        print("未输入模型，程序退出")
        return

    # 对话历史与执行环境
    history: list[dict] = []
    exec_globals = {"df": df, "pd": pd}

    print("请输入你的数据分析问题 (输入 'exit'或'quit' 结束):")
    while True:
        user_q = prompt(">>> ").strip()
        if user_q.lower() in {"exit", "quit"}:
            break
        if not user_q:
            continue

        print("正在向大模型请求... 请稍候。")
        try:
            result = ask(user_q, history, df, exec_globals, model)
        except Exception as e:
            print("发生错误:", e)
            continue

        if result["code"]:
            print("代码:\n", result["code"])
        if result["stdout"]:
            print("输出:\n", result["stdout"])
        print("解释:\n", result["explanation"])

    print("感谢使用，再见啦！")


if __name__ == "__main__":
    main() 