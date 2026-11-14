@echo off
REM Jal Awaaz on Windows. Usage: run.bat [install^|doctor^|run^|test^|test-e2e^|seed^|unseed^|smoke^|warm^|eval^|bench^|tunnel]
setlocal
cd /d "%~dp0"
if exist "..\.venv\Scripts\activate.bat" call "..\.venv\Scripts\activate.bat"
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"
set CMD=%1
if "%CMD%"=="" set CMD=run
if "%CMD%"=="install" ( python -m pip install -r requirements-dev.txt & goto :eof )
if "%CMD%"=="doctor" ( python -m scripts.doctor & goto :eof )
if "%CMD%"=="run" ( python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 & goto :eof )
if "%CMD%"=="test" ( python -m pytest -q --ignore=tests/e2e & goto :eof )
if "%CMD%"=="test-e2e" ( python -m pytest -q tests/e2e & goto :eof )
if "%CMD%"=="seed" ( python -m scripts.seed_demo & goto :eof )
if "%CMD%"=="unseed" ( python -m scripts.seed_demo --clear & goto :eof )
if "%CMD%"=="smoke" ( python -m scripts.smoke & goto :eof )
if "%CMD%"=="warm" ( python -m scripts.warm_tts & goto :eof )
if "%CMD%"=="eval" ( python -m bench.text_eval & goto :eof )
if "%CMD%"=="bench" ( python -m bench.make_noisy && python -m bench.run_bench & goto :eof )
if "%CMD%"=="tunnel" ( cloudflared tunnel --url http://localhost:8000 & goto :eof )
echo Unknown command "%CMD%". Use: install doctor run test test-e2e seed unseed smoke warm eval bench tunnel
