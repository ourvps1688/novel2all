# Force-remove .pytest_cache directory (Read-Only / EPERM)
$path = 'D:\OHMYSTORY\novel2all\.pytest_cache'
$log = 'D:\OHMYSTORY\novel2all\scripts\_del_cache.log'

"=== Deleting $path ===" | Out-File -FilePath $log -Encoding utf8
if (Test-Path $path) {
    try {
        # Take ownership and grant full control
        $acl = Get-Acl $path
        $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
            $env:USERNAME, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
        $acl.SetAccessRule($rule)
        Set-Acl -Path $path -AclObject $acl -ErrorAction SilentlyContinue
        # Clear read-only flag recursively
        Get-ChildItem -Path $path -Recurse -Force -ErrorAction SilentlyContinue |
            ForEach-Object { $_.Attributes = 'Normal' -bor $_.Attributes }
        $path.Attributes = 'Normal'
        # Remove
        Remove-Item -Path $path -Recurse -Force -ErrorAction Stop
        "REMOVED" | Out-File -FilePath $log -Append -Encoding utf8
    } catch {
        "FAILED: $_" | Out-File -FilePath $log -Append -Encoding utf8
    }
} else {
    "DOES NOT EXIST" | Out-File -FilePath $log -Append -Encoding utf8
}
"=== DONE ===" | Out-File -FilePath $log -Append -Encoding utf8
