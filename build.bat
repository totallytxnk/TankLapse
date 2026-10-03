@echo off
pyinstaller --noconfirm --clean ^
  --name TankLapse ^
  --windowed ^
  --onefile ^
  --hidden-import=mss ^
  --hidden-import=mss.windows ^
  --hidden-import=PIL ^
  --hidden-import=PIL.Image ^
  run.py

echo.
echo Done → dist\TankLapse.exe
pause