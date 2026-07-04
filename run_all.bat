@echo off
rem All/Agent をワンクリックで全部起動する:
rem   1. AI部下ワーカー (自動投稿の実行体) を別ウィンドウで起動
rem   2. サーバー (iPhoneからの窓口・Tailscale固定URL) をこのウィンドウで起動
cd /d "%~dp0"
title All/Agent 一括起動
start "All/Agent AI部下ワーカー" cmd /c run_agent.bat
python stable.py
pause
