@echo off
rem PCの起動時に All/Agent (ワーカー+サーバー) を自動起動させる設定。
rem スタートアップフォルダに起動用バッチを置くだけ (管理者権限不要)。
rem 解除したい場合は下の場所から AllAgent_autostart.bat を削除してください。
cd /d "%~dp0"
set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
(
  echo @echo off
  echo start "" "%~dp0run_all.bat"
) > "%STARTUP%\AllAgent_autostart.bat"
echo 設定しました。次回のPC起動から All/Agent が自動で立ち上がります。
echo   場所: %STARTUP%\AllAgent_autostart.bat
pause
