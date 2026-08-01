@echo off
chcp 65001 >nul
set DEBUG_MODE=1
setlocal EnableDelayedExpansion
chcp 936 >nul 2>&1

set "R=[91m" & set "G=[92m" & set "Y=[93m"
set "B=[94m" & set "M=[95m" & set "C=[96m"
set "W=[97m" & set "D=[90m" & set "N=[0m"
set "BD=[1m"

reg add HKCU\Console /v VirtualTerminalLevel /t REG_DWORD /d 1 /f >nul 2>&1
title XMAPort 260801.Beta

set "TD=%~dp0"
set "WK=%TD%workspace\"
for /f "tokens=1-3 delims=/ " %%a in ('date /t') do set "LOG_DATE=%%a-%%b-%%c"
for /f "tokens=1 delims=: " %%h in ('time /t') do set "LOG_HOUR=%%h"
set "LOG_FILE=%WK%%LOG_DATE%-%LOG_HOUR%.log"

:: Unified logging: INFO only when DEBUG_MODE=1, ERROR always shown.
if not defined DEBUG_MODE set "DEBUG_MODE=0"
set "INFO=echo  %G%[INFO]%N%  "
if not "%DEBUG_MODE%"=="1" set "INFO=rem "
set "ERR=echo  %R%[ERROR]%N% "

set "TK=%TD%tools\"
set "WK=%TD%workspace\"
set "CONFIG=%TD%config.ini"
set "ARIA2=%TK%aria2c.exe"
set "SZ=%TK%7z.exe"
set "PDUMP=%TK%payload-dumper-go.exe"
set "S2I=%TK%simg2img.exe"
set "I2S=%TK%img2simg.exe"
set "LPU=%TK%lpunpack.exe"
set "LPM=%TK%lpmake.exe"
set "LPD=%TK%lpdumps.exe"
set "HLP=%TK%img_helper.py"
set "PY=python"
set "SRC_DL=%WK%download_source"
set "TGT_DL=%WK%download_target"
set "SRC_ROM=%WK%source_rom"
set "TGT_ROM=%WK%target_rom"
set "SRC_UNPACK=%WK%source_payload"
set "TGT_UNPACK=%WK%target_payload"
set "OUT_DIR=%WK%output"
set "SRC_FS=%WK%source_filesystem"
set "TGT_FS=%WK%target_filesystem"
set "PACK_OUT=%WK%packed"
for %%d in ("%WK%" "%SRC_DL%" "%TGT_DL%" "%SRC_ROM%" "%TGT_ROM%" "%SRC_UNPACK%" "%TGT_UNPACK%" "%OUT_DIR%" "%SRC_FS%" "%TGT_FS%" "%PACK_OUT%") do if not exist "%%~d" mkdir "%%~d"

:Menu
cls
echo.
echo  %C%%BD%  ============================================================%N%
echo  %C%%BD%   _____              _   _   _                          %N%
echo  %C%%BD%  ^|__  /___ _ __ ___ ^| ^| ^| ^| ^| ^|__  _   _ _ __   ___ _ __ %N%
echo  %C%%BD%    / // _ \ '__/ _ \^| ^|_^| ^| ^| '_ \^| ^| ^| ^| '_ \ / _ \ '__^|%N%
echo  %C%%BD%   / /^|  __/ ^| ^| (_) ^|  _  ^| ^| ^| ^| ^| ^|_^| ^| ^|_) ^|  __/ ^|   %N%
echo  %C%%BD%  /____\___^|_^|  \___/^|_^| ^|_^| ^|_^| ^|_^|\__, ^| .__/ \___^|_^|   %N%
echo  %C%%BD%                                  ^|___/^|_^|              %N%
echo  %C%%BD%  ============================================================%N%
echo.
echo  %G%%BD%  [1] Done Port HyperOS%N%        %D%Full auto workflow%N%
echo.
echo  %Y%%BD%  -- Tools --%N%
echo  %W%  [A] Check Tools%N%
echo  %W%  [B] Open Workspace%N%
echo  %W%  [C] Open-Source Credits%N%
echo  %W%  [D] Clean workspace%N%
echo  %R%  [0] Exit%N%
echo.
echo  %C%%BD%  ============================================================%N%
echo.
set /p "CH=  %Y%%BD%Select [0-1, A-C]: %N%"

if "%CH%"=="1" goto OneClickPort
if /i "%CH%"=="A" goto ToolStatus
if /i "%CH%"=="B" explorer "%WK%"
if /i "%CH%"=="B" goto Menu
if /i "%CH%"=="C" goto ShowCredits
if /i "%CH%"=="D" goto CleanWorkspace
if "%CH%"=="0" goto Exit
echo  %R%  Invalid input%N%
timeout /t 1 >nul
goto Menu

:OneClickPort
cls
call :LogWrite "========== XMAport Session Start =========="
call :LogWrite "Target Device: !TARGET_DEVICE!"
echo.
echo  %C%%BD%  ============================================================%N%
echo  %C%%BD%    Done HyperOS%N%
echo  %C%%BD%  ============================================================%N%
echo.
echo  %W%  Workflow:%N%
echo  %G%    Step 1%N%  Download ROM packages
echo  %G%    Step 2%N%  Extract archives
echo  %G%    Step 3%N%  Extract payload.bin
echo  %G%    Step 4%N%  Extract archivesSource
echo  %G%    Step 5%N%  Extract archivesSource
echo  %G%    Step 6%N%  Extract archivesSource
echo  %G%    Step 7%N%  Success
echo.
echo  %D%  ----------------------------------------------------------%N%
echo.

:: Python environment check
%INFO% Checking Python environment...
"%PY%" --version >nul 2>&1
if errorlevel 1 (
    %ERR% Python not found! Please install Python 3.8+ and add it to PATH.
    echo  %W%  Download: %C%https://www.python.org/downloads/%N%
    pause
    goto Menu
)
for /f "tokens=*" %%v in ('"%PY%" --version 2^>^&1') do set "PYVER=%%v"
%INFO% Python OK: !PYVER!

if not exist "%CONFIG%" (
    %ERR% config.ini not found, creating a template
    call :CreateConfig
    echo  %Y%  [!] Edit config.ini first%N%
pause
goto Menu
)

call :ReadConfig

call :ReadPackingConfig

if not exist "%WK%config.txt" echo  %W%  Enter target device codename:%N%
if not exist "%WK%config.txt" echo  %D%  (e.g. sheng, fuxi, cupid, mondrian)%N%
if not exist "%WK%config.txt" set /p "TARGET_DEVICE=  > "
if not exist "%WK%config.txt" echo TARGET_DEVICE=!TARGET_DEVICE!> "%WK%config.txt"
for /f "tokens=2 delims==" %%a in ('findstr "TARGET_DEVICE" "%WK%config.txt" 2^>nul') do set "TARGET_DEVICE=%%a"

echo  %W%  Source URL:   %C%%SRC_URL:~0,50%%N%
echo  %W%  Target URL:   %C%%TGT_URL:~0,50%%N%
echo  %W%  Device:   %G%%TARGET_DEVICE%%N%
echo  %W%  Format1:   %G%!PACK_FORMAT!%N%  Compression: %G%!PACK_COMPRESS_ALG! level !PACK_COMPRESS!%N%  Pack super: %G%!PACK_SUPER!%N%
echo.
set /p "OC=  %Y%SuccessSource(Y/N): %N%"
if /i not "!OC!"=="Y" goto Menu

:: Step 1: Download
%INFO% === Step 1/7: Download ROM ===
call :LogWrite "Step 1: Download ROM start"
call :LogWrite "Source URL: %SRC_URL%"
call :LogWrite "Target URL: %TGT_URL%"
if not "%SRC_URL%"=="" (
    %INFO% [1/2] Downloading source ROM...
    call :DL_One "%SRC_URL%" "%SRC_DL%" "SourceROM"
    if errorlevel 1 %ERR% Step 1 failed: source ROM download
    if errorlevel 1 call :LogWrite "ERROR: Source ROM download failed"
    if errorlevel 1 pause
    if errorlevel 1 goto Menu
)
if not "%TGT_URL%"=="" (
    %INFO% [2/2] Downloading target ROM...
    call :DL_One "%TGT_URL%" "%TGT_DL%" "TargetROM"
    if errorlevel 1 %ERR% Step 1 failed: target ROM download
    if errorlevel 1 call :LogWrite "ERROR: Target ROM download failed"
    if errorlevel 1 pause
    if errorlevel 1 goto Menu
)
%INFO% Step 1 done
call :LogWrite "Step 1: Download ROM done"

:: Step 2: Extract
%INFO% === Step 2/7: Extract archives ===
call :LogWrite "Step 2: Extract archives start"
%INFO% [1/2] Extracting source archive...
call :ExtractArchive "%SRC_DL%" "%SRC_ROM%" "Source"
%INFO% [2/2] Extracting target archive...
call :ExtractArchive "%TGT_DL%" "%TGT_ROM%" "Target"
%INFO% Step 2 done
call :LogWrite "Step 2: Extract archives done"

:: Step 3: Payload
%INFO% === Step 3/7: Extract payload ===
call :LogWrite "Step 3: Extract payload start"

call :CheckPayloadExtracted "%SRC_UNPACK%"
if errorlevel 1 (
    %INFO% [1/2] Extracting source payload...
    call :ExtractPayloadBin "%SRC_ROM%" "%SRC_UNPACK%"
    call :LogWrite "Source payload extracted to: %SRC_UNPACK%"
)

call :CheckPayloadExtracted "%TGT_UNPACK%"
if errorlevel 1 (
    %INFO% [2/2] Extracting target payload...
    call :ExtractPayloadBin "%TGT_ROM%" "%TGT_UNPACK%"
    call :LogWrite "Target payload extracted to: %TGT_UNPACK%"
)

%INFO% Step 3 done
call :LogWrite "Step 3: Extract payload done"


:: Step 4: Unpack
%INFO% === Step 4/7: Unpack IMG ===
call :LogWrite "Step 4: Unpack IMG start"
%INFO% Unpacking source images...
call :UnpackAllIMG "%SRC_UNPACK%" "%SRC_FS%" "Source"
call :LogWrite "Source images unpacked to: %SRC_FS%"
%INFO% Unpacking target images...
call :UnpackAllIMG "%TGT_UNPACK%" "%TGT_FS%" "Target"
call :LogWrite "Target images unpacked to: %TGT_FS%"
%INFO% Step 4 done
call :LogWrite "Step 4: Unpack IMG done"

:: Step 5: Migrate
%INFO% === Step 5/7: Migrate ===
call :LogWrite "Step 5: Migrate start"
set "MIGRATE_OK=0"
set "MIGRATE_FAIL=0"

"%TK%make_hyper.exe" speed

if not errorlevel 1 (
    set /a MIGRATE_OK+=1
    call :LogWrite "make_hyper.exe speed: SUCCESS"
) else (
    set /a MIGRATE_FAIL+=1
    %ERR% Step 5 failed: make_hyper.exe speed returned an error
    call :LogWrite "ERROR: make_hyper.exe speed failed"
    pause
)

%INFO% Step 5 done. Success: !MIGRATE_OK! , Fail: !MIGRATE_FAIL!
call :LogWrite "Step 5: Migrate done (OK=!MIGRATE_OK!, Fail=!MIGRATE_FAIL!)"

call :InjectAdbDebug

:: Step 6: Pack partitions and create super.img (optional, config.ini [packing] pack_super)
%INFO% === Step 6/7: Pack partitions ===

%INFO% Format: !PACK_FORMAT! , Compression: !PACK_COMPRESS_ALG! level !PACK_COMPRESS!

%INFO% Cleaning packed directory...
del /q "%PACK_OUT%\*.img" 2>nul

set "PACK_OK=0"
set "PACK_FAIL=0"
set "LPC_ARGS="

:: Pack source partitions (always runs)
call :LogWrite "Packing source partitions: system, system_ext, product"
for %%p in (system system_ext product) do (
    if exist "%SRC_FS%\%%p" (
        %INFO% Packing partition: %%p
        call :LogWrite "Packing %%p..."
        "%PY%" "%TK%pack_partitions.py" "!PACK_FORMAT!" "!PACK_COMPRESS_ALG!,!PACK_COMPRESS!" "%SRC_FS%\%%p" "%PACK_OUT%" "!PACK_EXT4_PACKER!"
        if !errorlevel! neq 0 (
            %ERR% %%p: pack_partitions.py failed
            call :LogWrite "ERROR: %%p packing failed"
            set /a PACK_FAIL+=1
        ) else if not exist "%PACK_OUT%\%%p.img" (
            %ERR% %%p: output image not found
            call :LogWrite "ERROR: %%p.img not generated"
            set /a PACK_FAIL+=1
        ) else (
            if /i "%%p"=="system_ext" if /i "!PACK_SKIP_APEX!"=="true" (
                if exist "%SRC_UNPACK%\system_ext.img" (
                    copy /y "%SRC_UNPACK%\system_ext.img" "%PACK_OUT%\system_ext.img" >nul 2>&1
                    if not errorlevel 1 (
                        %INFO% is_skip_apex=true: system_ext.img replaced by source payload image
                        call :LogWrite "system_ext.img replaced by source payload (is_skip_apex=true)"
                    ) else (
                        %ERR% is_skip_apex=true but overwrite failed
                        call :LogWrite "WARNING: system_ext.img overwrite failed"
                    )
                ) else (
                    %ERR% is_skip_apex=true but source system_ext.img not found
                    call :LogWrite "WARNING: source system_ext.img not found for skip_apex"
                )
            )
            for %%f in ("%PACK_OUT%\%%p.img") do set "FSIZE=%%~zf"
            %INFO% %%p.img packed, !FSIZE! bytes
            call :LogWrite "%%p.img packed: !FSIZE! bytes"
            set "LPC_ARGS=!LPC_ARGS! --partition=%%p:readonly:!FSIZE!:!PACK_GROUP! --image=%%p=%PACK_OUT%\%%p.img"
            set /a PACK_OK+=1
        )
    )
)
:: Pack odm from target filesystem (always runs)
call :LogWrite "Packing odm from target filesystem"
%INFO% Packing partition: odm
if exist "%TGT_FS%\odm" (
    "%PY%" "%TK%pack_partitions.py" "!PACK_FORMAT!" "!PACK_COMPRESS_ALG!,!PACK_COMPRESS!" "%TGT_FS%\odm" "%PACK_OUT%" "!PACK_EXT4_PACKER!"
    if !errorlevel! neq 0 (
        %ERR% odm: pack_partitions.py failed
        call :LogWrite "ERROR: odm packing failed"
        set /a PACK_FAIL+=1
    ) else if not exist "%PACK_OUT%\odm.img" (
        %ERR% odm: output image not found
        call :LogWrite "ERROR: odm.img not generated"
        set /a PACK_FAIL+=1
    ) else (
        for %%f in ("%PACK_OUT%\odm.img") do set "VSIZE=%%~zf"
        %INFO% odm.img packed, !VSIZE! bytes
        call :LogWrite "odm.img packed: !VSIZE! bytes"
        set "LPC_ARGS=!LPC_ARGS! --partition=odm:readonly:!VSIZE!:!PACK_GROUP! --image=odm=%PACK_OUT%\odm.img"
        set /a PACK_OK+=1
    )
) else (
    %ERR% odm not found in target filesystem
    pause
)
:: Copy mi_ext from source payload (always runs)
call :LogWrite "Copying mi_ext from source payload"
%INFO% Adding mi_ext from source payload...

if exist "%SRC_UNPACK%\mi_ext.img" (
    copy /y "%SRC_UNPACK%\mi_ext.img" "%PACK_OUT%" >nul 2>&1
    if exist "%PACK_OUT%\mi_ext.img" (
        for %%f in ("%PACK_OUT%\mi_ext.img") do set "VSIZE=%%~zf"
        %INFO% mi_ext.img ready, !VSIZE! bytes
        call :LogWrite "mi_ext.img ready: !VSIZE! bytes"
        set "LPC_ARGS=!LPC_ARGS! --partition=mi_ext:readonly:!VSIZE!:!PACK_GROUP! --image=mi_ext=%PACK_OUT%\mi_ext.img"
    ) else (
        %ERR% mi_ext.img copy failed
        pause
    )
) else (
    %ERR% mi_ext.img not found in source payload
    pause
)

:: Copy vendor from target payload (always runs)
call :LogWrite "Copying vendor from target payload"
%INFO% Adding vendor from target payload...

if exist "%TGT_UNPACK%\vendor.img" (
    copy /y "%TGT_UNPACK%\vendor.img" "%PACK_OUT%" >nul 2>&1
    if exist "%PACK_OUT%\vendor.img" (
        for %%f in ("%PACK_OUT%\vendor.img") do set "VSIZE=%%~zf"
        %INFO% vendor.img ready, !VSIZE! bytes
        call :LogWrite "vendor.img ready: !VSIZE! bytes"
        set "LPC_ARGS=!LPC_ARGS! --partition=vendor:readonly:!VSIZE!:!PACK_GROUP! --image=vendor=%PACK_OUT%\vendor.img"
    ) else (
        %ERR% vendor.img copy failed
        pause
    )
) else (
    %ERR% vendor.img not found in target payload
    pause
)

if exist "%TGT_UNPACK%\vendor_dlkm.img" (
    copy /y "%TGT_UNPACK%\vendor_dlkm.img" "%PACK_OUT%" >nul 2>&1
    if exist "%PACK_OUT%\vendor_dlkm.img" (
        for %%f in ("%PACK_OUT%\vendor_dlkm.img") do set "VSIZE=%%~zf"
        %INFO% vendor_dlkm.img ready, !VSIZE! bytes
        call :LogWrite "vendor_dlkm.img ready: !VSIZE! bytes"
        set "LPC_ARGS=!LPC_ARGS! --partition=vendor_dlkm:readonly:!VSIZE!:!PACK_GROUP! --image=vendor_dlkm=%PACK_OUT%\vendor_dlkm.img"
    ) else (
        %ERR% vendor_dlkm.img copy failed
        pause
    )
) else (
    %ERR% vendor_dlkm.img not found in target payload
    pause
)

:: Create super.img (only if pack_super=true)
call :LogWrite "Creating super.img (pack_super=!PACK_SUPER!)"
if /i not "!PACK_SUPER!"=="true" goto Step7Summary
if !PACK_OK! EQU 0 (
    %ERR% No partitions packed, skipping super.img.
    call :LogWrite "WARNING: No partitions packed, super.img skipped"
    goto Step7Summary
)
%INFO% Creating super.img...
set "LPC_VAB="
if /i "!PACK_VIRTUAL_AB!"=="true" set "LPC_VAB=--virtual-ab"
set "LPC_SP="
if /i "!PACK_SPARSE!"=="true" set "LPC_SP=--sparse"
"%TK%lpmake.exe" --metadata-size !PACK_META_SIZE! --super-name !PACK_SUPER_NAME! --metadata-slots !PACK_META_SLOTS! --device !PACK_SUPER_NAME!:!PACK_DEVICE_SIZE! --group !PACK_GROUP!:!PACK_DEVICE_SIZE! !LPC_ARGS! !LPC_VAB! !LPC_SP! --output="%PACK_OUT%\super.img"
if errorlevel 1 (
    %ERR% lpmake failed
    call :LogWrite "ERROR: lpmake failed to create super.img"
    pause
    goto Step7Summary
)
call :LogWrite "super.img created successfully"
if /i "!PACK_SPARSE!"=="true" %INFO% sparse super.img created directly by lpmake
for %%f in ("%PACK_OUT%\super.img") do %INFO% super.img created, %%~zf bytes


:: Step 7: Summary
:Step7Summary
call :LogWrite "========== Porting Complete =========="
call :LogWrite "Total packed: !PACK_OK! partitions, !PACK_FAIL! failed"
call :LogWrite "Step 6: Pack partitions done"
call :LogWrite "Pack OK=!PACK_OK!, Fail=!PACK_FAIL!"
echo.
echo  %C%%BD%  ============================================================%N%
echo  %G%%BD%  Porting Complete!%N%
echo  %C%%BD%  ============================================================%N%
echo.
echo  %W%  Source FS:    %C%%SRC_FS%%N%
echo  %W%  Target FS:    %C%%TGT_FS%%N%
echo  %W%  Output:       %C%%PACK_OUT%\super.img%N%
echo.
for %%p in (system system_ext product odm mi_ext vendor vendor_dlkm) do (
    if exist "%PACK_OUT%\%%p.img" (
        for %%f in ("%PACK_OUT%\%%p.img") do echo  %G%    %%p.img  %%~zf bytes%N%
    )
)

:: ROM Info
echo  %C%  ---------- ROM Info ----------%N%
set "BP="
set "BP_ODM=%SRC_FS%\odm\etc\build.prop"
set "BP_PRD=%SRC_FS%\product\etc\build.prop"
set "BP_SYS=%SRC_FS%\system\system\build.prop"

if exist "%BP_ODM%" set "BP=%BP_ODM%"
if not defined BP if exist "%BP_PRD%" set "BP=%BP_PRD%"
if not defined BP if exist "%BP_SYS%" set "BP=%BP_SYS%"

if not defined BP (
    echo  %R%  [ERR] build.prop not found%N%
) else (
    for /f "tokens=1,* delims==" %%a in ('type "%BP%" 2^>nul ^| findstr /i "ro.product.odm.device"') do if "%%a"=="ro.product.odm.device" echo  %W%  device:     %C%%%b%N%
    for /f "tokens=1,* delims==" %%a in ('type "%BP%" 2^>nul ^| findstr /i "ro.product.odm.model"') do if "%%a"=="ro.product.odm.model" echo  %W%  model:      %C%%%b%N%
    for /f "tokens=1,* delims==" %%a in ('type "%BP%" 2^>nul ^| findstr /i "ro.product.odm.marketname"') do if "%%a"=="ro.product.odm.marketname" echo  %W%  marketname: %C%%%b%N%
    for /f "tokens=1,* delims==" %%a in ('type "%BP%" 2^>nul ^| findstr /i "ro.product.odm.brand"') do if "%%a"=="ro.product.odm.brand" echo  %W%  brand:      %C%%%b%N%
    for /f "tokens=1,* delims==" %%a in ('type "%BP%" 2^>nul ^| findstr /i "ro.product.odm.name"') do if "%%a"=="ro.product.odm.name" echo  %W%  name:       %C%%%b%N%
    for /f "tokens=1,* delims==" %%a in ('type "%BP%" 2^>nul ^| findstr /i "ro.product.odm.manufacturer"') do if "%%a"=="ro.product.odm.manufacturer" echo  %W%  vendor:     %C%%%b%N%
)
echo  %C%  ------------------------------%N%
echo.
echo  %C%%BD%  ============================================================%N%
echo.
pause
goto Menu


:: =============================================
::   Download with aria2c
::
::   Source: https://github.com/aria2/aria2
::   Success: GPL v2
::
::   %1=URL  %2=OutputDir  %3=DisplayName
:: =============================================
::   Pack one partition (called from for loop)
::   %1=partition name
:: =============================================
:DL_One
set "DL_URL=%~1" & set "DL_DIR=%~2" & set "DL_NAME=%~3"
set "DL_LOG=%TEMP%\aria2_%RANDOM%.log"
%INFO% Downloading: %DL_NAME%
start /B /WAIT "" "%ARIA2%" "%DL_URL%" -d "%DL_DIR%" -x %MAX_CONN% -s %THREADS% -j 1 --console-log-level=notice --summary-interval=1 --file-allocation=falloc --timeout=%TIMEOUT% --max-tries=%RETRY% --retry-wait=3 --continue=true --auto-file-renaming=false --allow-overwrite=true --log="%DL_LOG%" --log-level=notice
if errorlevel 1 %ERR% Download failed: %DL_NAME%
if errorlevel 1 del "%DL_LOG%" >nul 2>&1
if errorlevel 1 exit /b 1
%INFO% %DL_NAME% download done
for %%f in ("%DL_DIR%\*.*") do (
    %INFO%   %%~nxf  %%~zf bytes
)
del "%DL_LOG%" >nul 2>&1
exit /b 0


:: =============================================
::   Extract archive with 7-Zip
::
::   Source: https://www.7-zip.org/
::   Success: GNU LGPL
::
::   %1=SourceDir  %2=OutputDir  %3=Label
:: =============================================
:ExtractArchive
set "EA_SRC=%~1" & set "EA_DST=%~2" & set "EA_NAME=%~3"
set "EA_COUNT=0"
for %%f in ("%EA_SRC%\*.zip" "%EA_SRC%\*.tar" "%EA_SRC%\*.gz" "%EA_SRC%\*.tgz" "%EA_SRC%\*.7z" "%EA_SRC%\*.rar") do (
    if exist "%%f" (
        set /a EA_COUNT+=1
        %INFO% Processing: %%~nxf
        set "TMP_ARCHIVE=%%~sf"
        set "TMP_OUTDIR=%%~sf"
        for %%d in ("%EA_DST%") do set "TMP_OUTDIR=%%~sd"
        "%SZ%" x "!TMP_ARCHIVE!" -o"!TMP_OUTDIR!" -y >nul 2>&1
        if !errorlevel! equ 0 (
            %INFO% Extracted: %%~nxf
        ) else (
            %ERR% Extract failed: %%~nxf
        )
    )
)
if !EA_COUNT!==0 %ERR% No archives found in %EA_SRC%
if !EA_COUNT!==0 exit /b 1
exit /b 0


:: =============================================
::   Extract payload.bin
::
::   Source: https://github.com/ssut/payload-dumper-go
::   Success: MIT
::
::   %1=ROMDir  %2=OutputDir
:: =============================================
:ExtractPayloadBin
    set "EP_SRC=%~1"
    set "EP_DST=%~2"
set "EP_FILE="
for /r "%EP_SRC%" %%f in (payload.bin) do (if not defined EP_FILE set "EP_FILE=%%f")
if not defined EP_FILE (
    %INFO% payload.bin not found, copying existing img files...
    set "EP_IMGS=0"
    for /r "%EP_SRC%" %%f in (*.img) do (set /a EP_IMGS+=1 & copy "%%f" "%EP_DST%" >nul 2>&1)
    exit /b 0
)
%INFO% Found payload: %EP_FILE%
%INFO% Extracting payload.bin...
for %%i in ("%EP_FILE%") do set "EP_SHORT=%%~si"
for %%i in ("%EP_DST%") do set "ED_SHORT=%%~si"
"%PDUMP%" -o "%ED_SHORT%" "%EP_SHORT%"
if errorlevel 1 (
    %ERR% payload-dumper-go failed
    exit /b 1
)
%INFO% Payload extracted to: %EP_DST%
for %%f in ("%EP_DST%\*.img") do (for /f "delims=" %%m in ('powershell -NoProfile -Command "[math]::Round((Get-Item -LiteralPath '%%f').Length/1MB,1)"') do set "PSMB=%%m" & %INFO%   %%~nf.img  !PSMB! MB)
exit /b 0


:: =============================================
::   Unpack all partition IMGs
::
::   Uses extract_img.py for ext4 extraction
::
::   %1=IMGDir  %2=OutputDir  %3=Label
::
::   Successs: system, system_ext, product, odm,
::            (mi_ext, vendor, vendor_dlkm copied directly)
:: =============================================
:UnpackAllIMG
set "UA_SRC=%~1" & set "UA_DST=%~2" & set "UA_LABEL=%~3"
for %%p in (system system_ext product odm) do (
    if exist "%UA_SRC%\%%p.img" (
        %INFO% Processing %%p.img ...
        if not exist "%UA_DST%\%%p" mkdir "%UA_DST%\%%p"
        "%PY%" "%TK%extract_img.py" "%UA_SRC%\%%p.img" "%UA_DST%\%%p"
        if errorlevel 1 (
            %ERR% Failed to extract %%p.img
        ) else (
            %INFO% %%p.img extracted
        )
    )
)
exit /b 0


:: =============================================
::   Read config.ini
:: =============================================
:ReadConfig
set "SRC_URL="
set "TGT_URL="
set "THREADS=16" & set "MAX_CONN=16" & set "TIMEOUT=300" & set "RETRY=5"
set "IN_SOURCE="
set "IN_TARGET="
%INFO% Reading config.ini...
for /f "usebackq tokens=1,* delims==" %%a in ("%CONFIG%") do (
    set "key=%%a"
    set "val=%%b"
    if "!key!"=="[source]" (set "IN_SOURCE=1" & set "IN_TARGET=")
    if "!key!"=="[target]" (set "IN_TARGET=1" & set "IN_SOURCE=")
    if "!key!"=="[settings]" (set "IN_SOURCE=" & set "IN_TARGET=")
    if "!key!"=="[packing]" (set "IN_SOURCE=" & set "IN_TARGET=")
    if not "!key:~0,1!"==";" if not "!key:~0,1!"=="[" (
        if "!key!"=="url" (
            if defined IN_SOURCE set "SRC_URL=!val!"
            if defined IN_TARGET set "TGT_URL=!val!"
        )
    )
)
%INFO% Config loaded. SRC_URL=[%SRC_URL%]
%INFO% Config loaded. TGT_URL=[%TGT_URL%]
exit /b 0

:: =============================================
::   Read packing config
:: =============================================
:ReadPackingConfig
set "PACK_FORMAT=erofs" & set "PACK_COMPRESS_ALG=lz4hc" & set "PACK_COMPRESS=9" & set "PACK_READONLY=true"
set "PACK_DEVICE_SIZE=6979321856" & set "PACK_META_SIZE=65536" & set "PACK_SPARSE=true"
set "PACK_SUPER=false" & set "PACK_SUPER_NAME=super" & set "PACK_GROUP=main"
set "PACK_META_SLOTS=3" & set "PACK_VIRTUAL_AB=true"
set "PACK_EXT4_PACKER=make_ext4fs"
set "PACK_SKIP_APEX=false"
set "PACK_ADB_DEBUG=false"
set "IN_PACKING="
for /f "usebackq tokens=1,* delims==" %%a in ("%CONFIG%") do (
    set "key=%%a"
    set "val=%%b"

    if "%%a"=="[packing]" set "IN_PACKING=1"
    if "%%a"=="[source]" set "IN_PACKING="
    if "%%a"=="[target]" set "IN_PACKING="
    if "%%a"=="[settings]" set "IN_PACKING="

    if not "!key:~0,1!"==";" if not "!key:~0,1!"=="[" (
        if defined IN_PACKING (
            if "!key!"=="format" set "PACK_FORMAT=!val!"
            if "!key!"=="compression" set "PACK_COMPRESS_ALG=!val!"
            if "!key!"=="compression_level" set "PACK_COMPRESS=!val!"
            if "!key!"=="readonly" set "PACK_READONLY=!val!"
            if "!key!"=="device_size" set "PACK_DEVICE_SIZE=!val!"
            if "!key!"=="metadata_size" set "PACK_META_SIZE=!val!"
            if "!key!"=="sparse" set "PACK_SPARSE=!val!"
            if "!key!"=="pack_super" set "PACK_SUPER=!val!"
            if "!key!"=="super_name" set "PACK_SUPER_NAME=!val!"
            if "!key!"=="super_group" set "PACK_GROUP=!val!"
            if "!key!"=="metadata_slots" set "PACK_META_SLOTS=!val!"
            if "!key!"=="virtual_ab" set "PACK_VIRTUAL_AB=!val!"
            if "!key!"=="ext4_packer" set "PACK_EXT4_PACKER=!val!"
            if "!key!"=="is_skip_apex" set "PACK_SKIP_APEX=!val!"
            if "!key!"=="enable_adb_debug" set "PACK_ADB_DEBUG=!val!"
        )
    )
)
exit /b 0

:: =============================================
::   CheckPayloadExtracted
:: =============================================
:CheckPayloadExtracted
set "CP_DIR=%~1"
if not exist "%CP_DIR%" exit /b 1
set "CP_CNT=0"
for /r "%CP_DIR%" %%f in (*) do set /a CP_CNT+=1
if %CP_CNT% GTR 6 (
    %INFO% Already extracted ^(%CP_CNT% files^), skipping.
    exit /b 0
)
exit /b 1

:: =============================================
::   Create config.ini
:: =============================================
:CreateConfig
(
echo [source]
echo url=
echo.
echo [target]
echo url=
echo.
echo [settings]
echo threads=16
echo max-connection=16
echo timeout=300
echo retry=5
echo.
echo [packing]
echo pack_super=false
echo format=erofs
echo readonly=true
echo compression=lz4hc
echo compression_level=9
echo device_size=6979321856
echo metadata_size=65536
echo sparse=true
echo super_name=super
echo super_group=main
echo metadata_slots=3
echo virtual_ab=true
echo ext4_packer=make_ext4fs
echo is_skip_apex=false
echo enable_adb_debug=false
) > "%CONFIG%"
exit /b 0


:: =============================================
::   [A] PortingDone
:: =============================================
:ToolStatus
cls
echo.
echo  %C%  +----------------------------------------------------------+%N%
echo  %C%  ^|  PortingDone                                               ^|%N%
echo  %C%  +----------------------------------------------------------+%N%
echo.
echo  %W%  Tool                     Source%N%
echo  %D%  ----------------------------------------------------------%N%
call :CT "aria2c.exe"           "github.com/aria2/aria2"
call :CT "7z.exe"               "www.7-zip.org"
call :CT "payload-dumper-go.exe" "github.com/ssut/payload-dumper-go"
call :CT "simg2img.exe"         "AOSP system/core/libsparse"
call :CT "img2simg.exe"         "AOSP system/core/libsparse"
call :CT "lpunpack.exe"         "AOSP extras/partition_tools"
call :CT "lpmake.exe"           "AOSP extras/partition_tools"
call :CT "lpdumps.exe"          "AOSP extras/partition_tools"
call :CT "img_helper.py"        "SuccessSourcePythonSuccess"
call :CT "pack_partitions.py"   "SuccessSourcePythonDone"
echo  %D%  ----------------------------------------------------------%N%
pause
goto Menu

:CT
set "TN=%~1" & set "TS=%~2" & set "TP=%TK%%TN%"
if exist "%TP%" (
    for %%f in ("%TP%") do (
        if %%~zf GTR 0 (
            echo  %W%  %TN%  %G%[OK]%N%  %D%%TS%%N%
        ) else (
            echo  %W%  %TN%  %R%[N/A]%N%  %D%%TS%%N%
        )
    )
) else (
    echo  %W%  %TN%  %R%[N/A]%N%  %D%%TS%%N%
)
exit /b 0


:: =============================================
::   [C] Open-source credits
:: =============================================
:ShowCredits
cls
echo.
echo  %C%%BD%  ============================================================%N%
echo  %C%%BD%    Open-source credits%N%
echo  %C%%BD%  ============================================================%N%
echo.
echo  %G%  1. aria2c%N%
echo  %W%     SourcePorting%N%
echo  %C%     https://github.com/aria2/aria2%N%
echo  %D%     credit: GPL v2%N%
echo.
echo  %G%  2. 7-Zip (7z.exe)%N%
echo  %W%     DonePorting%N%
echo  %C%     https://www.7-zip.org/%N%
echo  %D%     credit: GNU LGPL%N%
echo.
echo  %G%  3. payload-dumper-go%N%
echo  %W%     Android OTA payload.bin SuccessPorting%N%
echo  %C%     https://github.com/ssut/payload-dumper-go%N%
echo  %D%     credit: MIT%N%
echo.
echo  %G%  4. AOSP partition tools%N%
echo  %W%     lpunpack, lpmake, lpdumps%N%
echo  %C%     https://github.com/nicktal01/aosp15_partition_tools%N%
echo  %D%     credit: Apache 2.0%N%
echo.
echo  %G%  5. MIO_KITCHEN SOURCE%N%
echo  %W%     img2simg, ext4.py, imgextractor.py%N%
echo  %C%     https://github.com/ColdWindScholar/MIO-KITCHEN-SOURCE
echo  %D%     credit: GPL %N%
echo.
echo  %D%  ----------------------------------------------------------%N%
pause
goto Menu

:CleanWorkspace
cls
echo.
echo  %Y%  This will delete all extracted .img and payload.bin files.%N%
echo  %Y%  Including:%N%
echo  %D%    - %SRC_UNPACK%\*.img%N%
echo  %D%    - %TGT_UNPACK%\*.img%N%
echo  %D%    - %SRC_ROM%\payload.bin%N%
echo  %D%    - %TGT_ROM%\payload.bin%N%
echo  %D%    - %WK%config.txt%N%
echo.
set /p "CF=  %R%Are you sure? (Y/N): %N%"
if /i not "!CF!"=="Y" goto Menu

%INFO% Cleaning workspace...
del /q "%SRC_UNPACK%\*.img" 2>nul
del /q "%TGT_UNPACK%\*.img" 2>nul
del /q "%SRC_ROM%\payload.bin" 2>nul
del /q "%TGT_ROM%\payload.bin" 2>nul
del /q "%WK%config.txt" 2>nul
%INFO% Workspace cleaned.
timeout /t 2 >nul
goto Menu

:Exit
cls
echo  %C%  ============================================================%N%
echo  %G%  Done HyperOS Porting!%N%
echo  %C%  ============================================================%N%
pause
exit

:: =============================================
::   Log writer
::   %1=message
:: =============================================
:LogWrite
>> "%LOG_FILE%" echo [%TIME%] %~1
exit /b 0

:: =============================================
::   Inject adb debug props into odm build.prop
::   (only when enable_adb_debug=true, never touch system)
:: =============================================
:InjectAdbDebug
set "ADB_BP=%TGT_FS%\odm\etc\build.prop"
if /i not "!PACK_ADB_DEBUG!"=="true" exit /b 0
if not exist "%ADB_BP%" (
    %ERR% enable_adb_debug=true but odm build.prop not found
    call :LogWrite "WARNING: adb debug inject skipped, build.prop not found"
    exit /b 0
)
findstr /c:"# XMAport adb debug" "%ADB_BP%" >nul 2>&1
if not errorlevel 1 (
    %INFO% adb debug props already injected, skipping
    call :LogWrite "adb debug props already present, skip"
    exit /b 0
)
(
    echo # XMAport adb debug
    echo ro.debuggable=1
    echo ro.secure=0
    echo ro.adb.secure=0
    echo persist.sys.usb.config=adb
    echo persist.adb.notify=0
    echo service.adb.root=1
    echo persist.sys.root_access=3
) >> "%ADB_BP%"
%INFO% adb debug props injected into odm build.prop
call :LogWrite "adb debug props injected: %ADB_BP%"
exit /b 0
