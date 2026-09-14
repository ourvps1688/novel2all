$ErrorActionPreference = 'Continue'
$logPath = 'D:\OHMYSTORY\novel2all\scripts\_patch_run.log'

# Run python patch script, capture all output
$pythonExe = 'D:\OHMYSTORY\novel2all\.venv\Scripts\python.exe'
$patchScript = 'D:\OHMYSTORY\novel2all\scripts\_p0_v2_apply.py'

"=== Running patch script ===" | Out-File -FilePath $logPath -Encoding utf8
try {
    & $pythonExe $patchScript 2>&1 | Out-File -FilePath $logPath -Append -Encoding utf8
    "=== EXIT CODE: $LASTEXITCODE ===" | Out-File -FilePath $logPath -Append -Encoding utf8
} catch {
    "=== EXCEPTION: $_ ===" | Out-File -FilePath $logPath -Append -Encoding utf8
}

"=== DONE ===" | Out-File -FilePath $logPath -Append -Encoding utf8
