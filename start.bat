@echo off
start "FastAPI" cmd /k "cd /d C:\market\api && python -m uvicorn main:app --port 8000"
start "Vite" cmd /k "cd /d C:\market\web && npm run dev"
timeout /t 5 /nobreak >nul
start "" "http://localhost:5173"
