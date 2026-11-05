@echo off
title Green Corridor - Public Internet Tunnel (Zero Wi-Fi Limit)
cd /d "%~dp0"
echo Starting Green Corridor Public Internet Tunnel...
python tunnel_runner.py
pause
