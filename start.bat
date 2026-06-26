@echo off
start "FastAPI" cmd /k "cd /d C:\market\api && python -m uvicorn main:app --port 8000 || (echo. && echo --- FASTAPI FAILED --- && pause)"
start "Vite" cmd /k "cd /d C:\market\web && npm run dev || (echo. && echo --- VITE FAILED --- && pause)"
timeout /t 5 /nobreak >nul
start "" "http://localhost:5173"
