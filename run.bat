@echo off
cd /d "%~dp0"
where py >nul 2>nul && (py -3 letter.py & goto :end)
where python >nul 2>nul && (python letter.py & goto :end)
echo.
echo Python was not found on this computer.
echo Install it from https://www.python.org/downloads/  (tick "Add Python to PATH")
echo Or just open index.html in your browser instead.
echo.
pause
:end
