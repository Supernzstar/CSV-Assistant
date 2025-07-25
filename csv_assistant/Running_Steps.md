# CSV Assistant 运行步骤说明

本项目提供两种使用方式：
1. 终端模式（CLI）  
2. 前后端 Web 应用模式（FastAPI + React）

---

## 0. 环境准备

### 0.1 Python 依赖

```bash
conda create -n ms python=3.13
conda activate ms
pip install -r requirements.txt
```

### 0.2 Node 依赖（仅 Web 模式）

```bash
cd frontend
npm install
cd ..
```

### 0.3 配置环境变量

```bash
# 必填
export OPENAI_API_KEY="sk-..."           # 你的 云雾 AP_Key

# 可选
export OPENAI_MODEL="gpt-4o"             # 默认使用的模型
export API_PORT=8000                      # 服务端口
export CSV_PATH=/absolute/path/to/data.csv  # 启动时自动加载的 CSV
```

---

## 1. 终端模式

```bash
python assistant.py ./data.csv   #（可任意更换csv文件的路径）
```
程序会提示输入要使用的大模型名称（如 `gpt-4o`），随后即可在提示符下与模型对话。  
输入 `exit` / `quit` 结束会话。

---

## 2. Web 应用模式

```bash
python cli.py
```
该脚本会自动：
1. 安装/更新前端依赖并完成 `npm run build`  
2. 启动 FastAPI (`api_server.py`)，默认地址 `http://127.0.0.1:8000`  
3. 自动打开浏览器

使用方法：
1. 访问浏览器：  
   - 构建模式: `http://127.0.0.1:8000`  
   - 开发模式: `http://127.0.0.1:5173`
2. 通过侧边栏上传 CSV，或使用 `/api/load_csv` 指定服务器上已有文件
3. 可任意选择不同模型
3. 在输入框输入自然语言问题，回车发送