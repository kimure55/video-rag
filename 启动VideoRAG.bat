@echo off
start /b cmd /c "cd backend && python -m uvicorn app.main:app --port 8000"
start /b cmd /c "cd frontend && npm run dev"
timeout /t 5
npm start