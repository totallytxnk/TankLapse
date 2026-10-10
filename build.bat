@echo off
echo Building TankLapse.exe ...
pyinstaller --noconfirm --clean ^
  --name TankLapse ^
  --windowed ^
  --onefile ^
  --paths . ^
  --collect-submodules tanklapse ^
  --collect-all mss ^
  --hidden-import=tanklapse ^
  --hidden-import=tanklapse.app ^
  --hidden-import=tanklapse.capture ^
  --hidden-import=tanklapse.video ^
  --hidden-import=mss ^
  --hidden-import=mss.windows ^
  --hidden-import=mss.linux ^
  --hidden-import=mss.darwin ^
  --hidden-import=PIL ^
  --hidden-import=PIL.Image ^
  run.py

echo.
echo Done → dist\TankLapse.exe
pause