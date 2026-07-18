@echo off
set "PYTHON_EXE=C:\Users\john\AppData\Local\Python\bin\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"
"%PYTHON_EXE%" "%~dp0dashboard_pipeline.py" %*