from __future__ import annotations

import os
import re
import traceback
from io import StringIO
from typing import List

import pandas as pd
import openai
from fastapi import FastAPI, HTTPException, APIRouter, UploadFile, File
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import base64
from contextlib import redirect_stdout

# --------------------------------------------------
# 环境变量
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("请先设置 OPENAI_API_KEY 环境变量")

client = openai.OpenAI(api_key=OPENAI_API_KEY,
                      base_url="https://yunwu.ai/v1")
                      
DEFAULT_MODEL = os.getenv("OPENAI_MODEL")  
DATA_PATH = os.getenv("CSV_PATH")  
OUTPUT_DIR = os.path.dirname(__file__) or "."


# --------------------------------------------------
# 加载数据
def load_dataframe(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    df = pd.read_csv(path)
    return df

if DATA_PATH and os.path.exists(DATA_PATH):
    df_global = load_dataframe(DATA_PATH)
else:
    df_global = pd.DataFrame()  # 空 DataFrame，等待用户上传/加载

# --------------------------------------------------
# 对话会话类
class AssistantSession:
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        self.history: List[dict] = []
        self.exec_globals = {"df": self.df, "pd": pd}

    def call_llm(self, messages, model: str | None = None):
        chosen_model = model or DEFAULT_MODEL
        if not chosen_model:
            raise RuntimeError("未指定模型，请在前端选择模型或设置 OPENAI_MODEL 环境变量")
        resp = client.chat.completions.create(
            model=chosen_model,
            messages=messages,
            temperature=0.1,
        )
        return resp.choices[0].message.content.strip()

    @staticmethod
    def extract_code(content: str) -> str | None:
        code_match = re.search(r"```python(.*?```)", content, re.S)
        if not code_match:
            code_match = re.search(r"```(.*?```)", content, re.S)
        if not code_match:
            return None
        code_block = code_match.group(1)
        code = re.sub(r"```", "", code_block).strip()
        return code

    def execute_python(self, code: str):
        stdout_buf = StringIO()
        err_trace = None
        try:
            with redirect_stdout(stdout_buf):
                exec(code, self.exec_globals)
        except Exception:
            err_trace = traceback.format_exc()
        return stdout_buf.getvalue(), err_trace

    def system_prompt(self) -> str:
        cols = ", ".join(self.df.columns)
        sample = self.df.head().to_string(index=False)
        return (
            "你是一名资深数据分析师，需要根据用户的自然语言指令，对已加载到变量 `df` 的 pandas DataFrame 数据进行分析。\n"
            f"当前 DataFrame 列: {cols}\n"
            f"前几行示例:\n{sample}\n\n"
            "规则：\n"
            "1. 不要重新读取 CSV；数据已在变量 df 中。\n"
            "2. 若需绘图，请直接在聊天框中输出，并使用 print 输出关键汇总信息。\n"
            "3. 仅返回 markdown 代码块，格式```python\n# code```。"
            "4. 如果用户的问题与 `df` 无关（聊天、编程、知识问答等），请像 ChatGPT 一样自然回答，不需要输出代码块。\n"
        )



    def ask(self, question: str, model: str | None = None):
        messages = [{"role": "system", "content": self.system_prompt()}]
        for h in self.history:
            messages += [
                {"role": "user", "content": h["question"]},
                {"role": "assistant", "content": f"```python\n{h['code']}\n```" if h["code"] else ""},
                {"role": "assistant", "content": h["stdout"]},
                {"role": "assistant", "content": h["explanation"]},
            ]
        
        messages.append({"role": "user", "content": question})

        # --- 图片检测：执行前 ---
        try:
            before_files = {f for f in os.listdir(OUTPUT_DIR) if f.endswith('.png')}
        except FileNotFoundError:
            before_files = set()

        assistant_reply = self.call_llm(messages, model)
        code = self.extract_code(assistant_reply)
        if not code:
            result = {"code": "", "stdout": "", "explanation": assistant_reply,"images":[]}
            self.history.append({**result, "question": question})
            return result

        max_retry = 5
        for _ in range(max_retry + 1):
            stdout, err = self.execute_python(code)
            if err is None:
                break
            messages.append({"role": "assistant", "content": f"前段代码报错信息:\n{err}"})
            assistant_reply = self.call_llm(messages, model)
            code = self.extract_code(assistant_reply) or code
        if err is not None:
            raise RuntimeError(f"代码仍有错误:\n{err}")

        # --- 图片检测：执行后 ---
        try:
            after_files = {f for f in os.listdir(OUTPUT_DIR) if f.endswith('.png')}
        except FileNotFoundError:
            after_files = set()

        new_image_files = list(after_files - before_files)
        generated_images_base64 = []
        for filename in new_image_files:
            filepath = os.path.join(OUTPUT_DIR, filename)
            try:
                with open(filepath, "rb") as image_file:
                    encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
                    generated_images_base64.append(f"data:image/png;base64,{encoded_string}")
            except Exception as e:
                print(f"Error processing image {filepath}: {e}")


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
                "content": (
                    "代码:\n```python\n" + code + "\n```\n\n执行输出:\n" + stdout
                ),
            },
        ]
        explanation = self.call_llm(explain_prompt, model)

        # 记录历史
        result = {"code": code, "stdout": stdout, "explanation": explanation,"images": generated_images_base64}
        self.history.append({**result, "question": question})

        return result


    def reset(self):
        self.history.clear()
        self.exec_globals = {"df": self.df.copy(), "pd": pd}

# --------------------------------------------------
# FastAPI 应用

app = FastAPI(title="Assistant API")

# --------- API router ---------
api_router = APIRouter(prefix="/api")

# 挂载前端静态文件
frontend_dist = Path(__file__).parent / "frontend" / "dist"
print(f"前端目录: {frontend_dist} {'存在' if frontend_dist.exists() else '不存在'}")

# 静态资源目录
if frontend_dist.exists():
    # 挂载静态资源目录
    assets_dir = frontend_dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    # 所有非 API 请求返回 index.html (SPA模式)
    @app.get("/")
    async def read_index():
        return FileResponse(frontend_dist / "index.html")
    
    # SPA前端路由支持 - 任何不匹配的路由返回index.html
    @app.get("/{path:path}")
    async def catch_all(path: str):
        # 跳过API和静态文件路径
        if path.startswith("api/") or path.startswith("assets/"):
            raise HTTPException(status_code=404, detail="Not Found")
        return FileResponse(frontend_dist / "index.html")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 创建一个空DataFrame作为初始状态
empty_df = pd.DataFrame()
session = AssistantSession(empty_df)

class AskRequest(BaseModel):
    question: str
    model: str | None = None


# use router
@api_router.post("/ask")
async def ask_api(req: AskRequest):
    try:
        res = session.ask(req.question, req.model)
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))



#
@api_router.post("/reset")
async def reset_session():
    session.reset()
    return {"message": "reset success"} 

class CSVPathRequest(BaseModel):
    paths: List[str]

@api_router.post("/load_csv")
async def load_csv(req: CSVPathRequest):
    """Load CSV file from given path on the server."""
    try:
        # 只使用第一个路径
        if not req.paths:
            raise HTTPException(status_code=400, detail="No path provided")
            
        path = req.paths[0]  # 只取第一个路径
        filename = os.path.basename(path)
        
        # Load the dataframe
        df = load_dataframe(path)
        
        # Replace the session
        global session
        session = AssistantSession(df)
        
        result = {
            "message": "CSV file loaded successfully",
            "files": [{
                "filename": filename,
                "path": path,
                "rows": df.shape[0],
                "columns": df.shape[1],
                "column_names": list(df.columns)
            }]
        }
        
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@api_router.post("/upload_csv")
async def upload_csv(file: UploadFile = File(...)):
    """Upload a single CSV file from the client and load it into the session."""
    try:
        filename = file.filename
        
        # Read the uploaded file directly into pandas
        df = pd.read_csv(file.file)
        
        # Optional: simple cleaning
        if "Sales" in df.columns:
            df["Sales"] = (
                df["Sales"].astype(str).str.replace(r"[^0-9.]+", "", regex=True).replace("", "0").astype(float)
            )
        if "Rating" in df.columns:
            df["Rating"] = (
                df["Rating"].astype(str).str.replace(r"[^0-9.]+", "", regex=True).replace("", "0").astype(float)
            )
        
        # 直接替换会话中的DataFrame
        global session
        session = AssistantSession(df)
        
        result = {
            "message": "CSV file uploaded and loaded successfully",
            "files": [{
                "filename": filename,
                "rows": df.shape[0],
                "columns": df.shape[1],
                "column_names": list(df.columns)
            }]
        }
        
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class ModelRequest(BaseModel):
    model: str

@api_router.post("/set_model")
async def set_model(req: ModelRequest):
    """Set the LLM model used for subsequent requests."""
    global DEFAULT_MODEL
    DEFAULT_MODEL = req.model
    return {"message": "model updated", "model": DEFAULT_MODEL}

# 注册 API router - 必须在定义路由后再注册
app.include_router(api_router) 