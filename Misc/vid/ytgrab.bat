@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ===========================
REM Settings
REM ===========================
set "SCRIPT_DIR=%~dp0"
set "TOOLS_DIR=%SCRIPT_DIR%tools"
set "DL_DIR=%SCRIPT_DIR%downloads"
set "YTDLP_EXE=%TOOLS_DIR%\yt-dlp.exe"
set "FFMPEG_DIR=%TOOLS_DIR%\ffmpeg"
set "FFMPEG_BIN=%FFMPEG_DIR%\bin"
set "FFMPEG_EXE=%FFMPEG_BIN%\ffmpeg.exe"

REM Stable "latest" URLs (official / widely used)
set "YTDLP_URL=https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
set "FFMPEG_ZIP_URL=https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

REM Create folders
if not exist "%TOOLS_DIR%" mkdir "%TOOLS_DIR%" >nul 2>&1
if not exist "%DL_DIR%" mkdir "%DL_DIR%" >nul 2>&1

REM ===========================
REM Dependency bootstrap
REM ===========================
call :ensure_ytdlp || goto :fatal
call :ensure_ffmpeg || goto :fatal

REM Add ffmpeg to PATH for this session
set "PATH=%FFMPEG_BIN%;%PATH%"

REM ===========================
REM Prompt for URL
REM ===========================
echo.
echo Paste a YouTube video URL or playlist URL, then press Enter:
set "INPUT_URL="
set /p "INPUT_URL=> "

if "%INPUT_URL%"=="" (
  echo.
  echo No URL entered. Exiting.
  goto :eof
)

REM Decide playlist vs single video:
REM If URL contains "list=", we treat it as a playlist
set "MODE_SINGLE=1"
echo "%INPUT_URL%" | findstr /I /C:"list=" >nul && set "MODE_SINGLE=0"

REM Output folder per run (timestamp-ish using %DATE%/%TIME% safe-ish)
call :make_run_folder RUN_OUTDIR || goto :fatal

echo.
echo Output folder:
echo   "%RUN_OUTDIR%"
echo.

REM ===========================
REM yt-dlp options
REM ===========================
REM Force MP4 container where possible; otherwise merge into MP4 using ffmpeg.
REM - Prefer mp4 video + m4a audio; fallback to best.
REM - Playlist: keep ordering via playlist_index in filename.
REM - Progress: line-by-line updates.
set "COMMON_OPTS=--no-part --newline --progress --console-title --restrict-filenames --ffmpeg-location "%FFMPEG_BIN%" --merge-output-format mp4"
set "FORMAT_OPTS=-f "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b""

REM Output templates:
REM Batch files require doubling percent signs: %%(...)
set "OUT_SINGLE=-o "%RUN_OUTDIR%\%%(title)s [%%(id)s].%%(ext)s""
set "OUT_PLAYLIST=-o "%RUN_OUTDIR%\%%(playlist_index)03d - %%(title)s [%%(id)s].%%(ext)s""

REM ===========================
REM Run download
REM ===========================
if "!MODE_SINGLE!"=="1" (
  echo Detected: Single video
  echo.
  "%YTDLP_EXE%" %COMMON_OPTS% %FORMAT_OPTS% %OUT_SINGLE% --no-playlist "%INPUT_URL%"
) else (
  echo Detected: Playlist
  echo.
  "%YTDLP_EXE%" %COMMON_OPTS% %FORMAT_OPTS% %OUT_PLAYLIST% --yes-playlist "%INPUT_URL%"
)

set "ERR=%ERRORLEVEL%"
echo.
if not "%ERR%"=="0" (
  echo Download finished with an error. Exit code: %ERR%
  goto :eof
)

echo Done.
goto :eof

REM ===========================
REM Functions
REM ===========================

:ensure_ytdlp
if exist "%YTDLP_EXE%" exit /b 0
echo yt-dlp not found. Downloading to:
echo   "%YTDLP_EXE%"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "try { iwr -UseBasicParsing -Uri '%YTDLP_URL%' -OutFile '%YTDLP_EXE%'; exit 0 } catch { exit 1 }"
if not exist "%YTDLP_EXE%" (
  echo Failed to download yt-dlp.
  exit /b 1
)
exit /b 0

:ensure_ffmpeg
if exist "%FFMPEG_EXE%" exit /b 0

echo FFmpeg not found. Downloading and extracting...
set "FF_ZIP=%TOOLS_DIR%\ffmpeg-release-essentials.zip"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "try { iwr -UseBasicParsing -Uri '%FFMPEG_ZIP_URL%' -OutFile '%FF_ZIP%'; exit 0 } catch { exit 1 }"
if not exist "%FF_ZIP%" (
  echo Failed to download FFmpeg zip.
  exit /b 1
)

REM Extract zip to a temp folder, then move/rename to tools\ffmpeg
set "FF_TMP=%TOOLS_DIR%\_ffmpeg_tmp"
if exist "%FF_TMP%" rmdir /s /q "%FF_TMP%" >nul 2>&1
mkdir "%FF_TMP%" >nul 2>&1

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "try { Expand-Archive -Force -LiteralPath '%FF_ZIP%' -DestinationPath '%FF_TMP%'; exit 0 } catch { exit 1 }"
if errorlevel 1 (
  echo Failed to extract FFmpeg zip.
  exit /b 1
)

REM The zip typically contains a single top folder named like "ffmpeg-*-essentials_build"
set "FOUND="
for /d %%D in ("%FF_TMP%\ffmpeg-*") do (
  set "FOUND=%%~fD"
  goto :ff_found
)

:ff_found
if "%FOUND%"=="" (
  echo Could not locate extracted FFmpeg folder layout.
  exit /b 1
)

if exist "%FFMPEG_DIR%" rmdir /s /q "%FFMPEG_DIR%" >nul 2>&1
move "%FOUND%" "%FFMPEG_DIR%" >nul
if not exist "%FFMPEG_EXE%" (
  echo FFmpeg extracted, but ffmpeg.exe was not found where expected:
  echo   "%FFMPEG_EXE%"
  exit /b 1
)

REM Cleanup zip + temp
del /q "%FF_ZIP%" >nul 2>&1
rmdir /s /q "%FF_TMP%" >nul 2>&1
exit /b 0

:make_run_folder
REM Returns a safe-ish timestamp folder name in the variable passed as %1
set "RAW_DATE=%DATE%"
set "RAW_TIME=%TIME%"

REM Build something like YYYY-MM-DD_HH-MM-SS using PowerShell for locale safety
for /f "usebackq delims=" %%T in (`powershell -NoProfile -Command "(Get-Date).ToString('yyyy-MM-dd_HH-mm-ss')"` ) do set "STAMP=%%T"

set "OUT=%DL_DIR%\%STAMP%"
if not exist "%OUT%" mkdir "%OUT%" >nul 2>&1

set "%~1=%OUT%"
exit /b 0

:fatal
echo.
echo A fatal error occurred. Exiting.
exit /b 1
