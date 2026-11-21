@echo off
setlocal
set "ENHANCED_SETUP=%~dp0Sources\Installer\SnowRunnerEnhanced.Setup.exe"
if not exist "%ENHANCED_SETUP%" (
  echo SnowRunner Enhanced: extract the complete ZIP before running Install.cmd.
  echo SnowRunner Enhanced : extrayez le ZIP complet avant de lancer Install.cmd.
  pause
  exit /b 2
)
"%ENHANCED_SETUP%" %*
set "ENHANCED_EXIT=%ERRORLEVEL%"
if not "%ENHANCED_EXIT%"=="0" if "%~1"=="" pause
exit /b %ENHANCED_EXIT%
