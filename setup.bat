@echo off
setlocal

echo Installing dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo.
echo Setup complete. Use run.bat to start the app.
pause
