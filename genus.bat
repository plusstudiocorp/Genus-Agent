@echo off
REM Change main.py to the main python files absolute path to use it anywhere.
REM And do not forget to add this file to path by running: --setx PATH "%PATH%;C:\Path\To\This\Folder" /m-- in cmd.
REM Change C:\Path\To\This\Folder to the absolute path where this genus.bat file exists.
python "%~dp0main.py"