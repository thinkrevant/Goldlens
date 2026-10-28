@echo off
rem Daily GoldLens brief + alerts to Telegram. Schedule with Windows Task Scheduler.
cd /d "%~dp0.."
python -m goldlens.notify >> data\notify.log 2>&1
