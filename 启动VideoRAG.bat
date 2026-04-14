@echo off
title Video RAG 导演中控台
color 0a

echo ==========================================
echo    正在唤醒 AI 大脑 (Backend)...
echo ==========================================
:: 启动后端，使用 start /b 让它在后台静默运行
start /b cmd /c "cd /d D:\UGit\Video RAG\backend && python -m uvicorn app.main:app --port 8000"

echo.
echo ==========================================
echo    正在搭建 灯光舞台 (Frontend)...
echo ==========================================
:: 启动前端 Vite
start /b cmd /c "cd /d D:\UGit\Video RAG\frontend && npm run dev"

echo.
echo ⏳ 等待 5 秒让服务稳一稳...
timeout /t 5 /nobreak > nul

echo.
echo ==========================================
echo    正在推入 监视器 (Electron)...
echo ==========================================
:: 启动 Electron 窗口
npm start

echo.
echo ✅ 全部就绪！导演请看监视器。
pause