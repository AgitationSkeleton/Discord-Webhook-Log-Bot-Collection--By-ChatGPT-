@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "toolDir=%~dp0"
set "ffmpegExe=%toolDir%ffmpeg.exe"
set "ffprobeExe=%toolDir%ffprobe.exe"

if not exist "%ffmpegExe%" goto noffmpeg
if not exist "%ffprobeExe%" goto noffprobe
if "%~1"=="" goto usage

set /a queueTotal=0
set /a queueOk=0
set /a queueSkip=0
set /a queueFail=0

echo ============================================================
echo Queue started: %DATE% %TIME%
echo ============================================================

:queueLoop
if "%~1"=="" goto queueDone

set /a queueTotal+=1
echo.
echo ------------------------------------------------------------
echo [%queueTotal%] "%~f1"
echo ------------------------------------------------------------

call :processOne "%~1"
set "rc=%ERRORLEVEL%"

if "%rc%"=="0" (
  set /a queueOk+=1
) else if "%rc%"=="2" (
  set /a queueSkip+=1
) else (
  set /a queueFail+=1
)

shift
goto queueLoop

:queueDone
echo.
echo ============================================================
echo Queue finished: %DATE% %TIME%
echo   Total: %queueTotal%
echo   OK   : %queueOk%
echo   Skip : %queueSkip%
echo   Fail : %queueFail%
echo ============================================================
echo.
pause >nul
exit /b 0


:processOne
set "inputFull=%~f1"
set "inputDir=%~dp1"
set "inputExt=%~x1"
set "inputBase=%~n1"

set "outDir=%inputDir%"
if exist "%inputDir%mp4\" set "outDir=%inputDir%mp4\"

set "outputFile=%outDir%%inputBase% (converted).mp4"
set "logFile=%outputFile%.log"

echo ------------------------------------------------------------ > "%logFile%"
echo Input : "%inputFull%" >> "%logFile%"
echo Output: "%outputFile%" >> "%logFile%"
echo ------------------------------------------------------------ >> "%logFile%"

if not exist "%inputFull%" (
  echo ERROR: File not found: "%inputFull%"
  echo ERROR: File not found >> "%logFile%"
  exit /b 1
)

if /I not "%inputExt%"==".mkv" (
  echo SKIP: Not an MKV
  echo SKIP: Not an MKV >> "%logFile%"
  exit /b 2
)

REM Skip if the input name already looks like a converted output
echo "%inputBase%" | findstr /i /c:" (converted)" >nul
if not errorlevel 1 (
  echo SKIP: Input already looks converted
  echo SKIP: Input already looks converted >> "%logFile%"
  exit /b 2
)

REM Skip if output already exists
if exist "%outputFile%" (
  echo SKIP: Output already exists: "%outputFile%"
  echo SKIP: Output already exists >> "%logFile%"
  exit /b 2
)

echo Converting (no subtitles)... (log: "%logFile%")
echo Converting (no subtitles)... >> "%logFile%"

"%ffmpegExe%" -hide_banner -y ^
  -i "%inputFull%" ^
  -map 0:v:0 -map 0:a? ^
  -c:v libx264 -preset medium -crf 20 ^
  -c:a aac -b:a 192k ^
  -movflags +faststart ^
  "%outputFile%" >> "%logFile%" 2>>&1

if errorlevel 1 (
  echo ERROR: Conversion failed. See log: "%logFile%"
  exit /b 1
)

echo OK: "%outputFile%"
exit /b 0


:noffmpeg
echo ERROR: ffmpeg.exe not found next to this BAT:
echo   "%ffmpegExe%"
pause >nul
exit /b 1

:noffprobe
echo ERROR: ffprobe.exe not found next to this BAT:
echo   "%ffprobeExe%"
pause >nul
exit /b 1

:usage
echo Drag and drop one or more MKV files onto this BAT, or run:
echo   mkv_to_mp4_nosubs.bat "file1.mkv" "file2.mkv" ...
pause >nul
exit /b 0
