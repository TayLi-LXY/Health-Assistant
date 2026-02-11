@echo off
cd /d "%~dp0..\frontend"
if not exist node_modules (
    echo 正在安装依赖...
    npm install
)
npm run dev
