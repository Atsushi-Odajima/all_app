@echo off
cd /d "%~dp0"
title All/Agent AI部下ワーカー
echo AI部下ワーカーを起動します (このウィンドウは開いたままにしてください)
python agent_worker.py
pause
