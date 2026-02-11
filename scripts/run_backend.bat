@echo off
cd /d "%~dp0..\backend"
if not exist venv (
    echo 正在创建虚拟环境...
    python -m venv venv
)
call venv\Scripts\activate
pip install -r requirements.txt -q
if not exist .env (
    copy .env.example .env
    echo 已创建 .env 文件，请编辑并填入 DEEPSEEK_API_KEY
    pause
)
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
