@echo off
title ComicScraper WebUI
echo Activating virtual environment...
call venv\Scripts\activate

echo Starting ComicScraper WebUI...
echo Opening browser at http://127.0.0.1:7860
start "" "http://127.0.0.1:7860"
python app.py

echo.
echo Application closed.
pause
