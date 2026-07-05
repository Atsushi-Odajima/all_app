@echo off
rem All/Agent をワンクリックで全部起動する。
rem サーバー(stable.py)が AI部下ワーカーを子プロセスとして自動起動・監視する
rem ため、これ1つでサーバーとワーカーの両方が立ち上がる。
cd /d "%~dp0"
title All/Agent
python stable.py
pause
