@echo off
rem Closes the HemoScan API and simulator windows.
taskkill /F /FI "WINDOWTITLE eq HemoScan API*" >nul 2>nul
taskkill /F /FI "WINDOWTITLE eq HemoScan ESP32 simulator*" >nul 2>nul
echo HemoScan stopped.
timeout /t 2 >nul
