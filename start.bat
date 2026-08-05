@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  call .venv\Scripts\pip.exe install -r requirements.txt
)
REM Keep local traffic away from system proxy.
set NO_PROXY=127.0.0.1,localhost
set no_proxy=127.0.0.1,localhost
set HTTP_PROXY=
set HTTPS_PROXY=
set ALL_PROXY=
set http_proxy=
set https_proxy=
set all_proxy=
set GPT_LINK_PORT=8801
start "" "http://127.0.0.1:8801"
".venv\Scripts\python.exe" app.py
pause
