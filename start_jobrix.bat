@echo off
cd /d C:\Users\rajve\JobRix
call .venv\Scripts\activate.bat
set "GEMINI_API_KEY="
for /f "delims=" %%K in ('powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('GEMINI_API_KEY','User')"') do set "GEMINI_API_KEY=%%K"
if not defined GEMINI_API_KEY (
    echo ERROR: GEMINI_API_KEY not found.
    pause
    exit /b 1
)
streamlit run app.py
pause
