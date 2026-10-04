$ErrorActionPreference = 'Continue'
$distro = 'Ubuntu-24.04'
$root = '/opt/aiden-wake-training'

while ($true) {
    Clear-Host
    Write-Host 'Aiden wake-model training monitor' -ForegroundColor Cyan
    Get-Date

    Write-Host "`nProcess"
    & wsl.exe -d $distro -u root -- bash -lc "ps -eo etime,pcpu,pmem,cmd | grep -E 'openwakeword/train.py|train_wake_word_v2.sh' | grep -v grep || true"

    Write-Host "`nGenerated files"
    & wsl.exe -d $distro -u root -- bash -lc "find $root/aiden_v2_output -type f 2>/dev/null | wc -l"

    Write-Host "`nOutput size"
    & wsl.exe -d $distro -u root -- bash -lc "du -sh $root/aiden_v2_output 2>/dev/null || true"

    Write-Host "`nDisk"
    & wsl.exe -d $distro -u root -- bash -lc "df -h / | tail -1"
    Start-Sleep -Seconds 10
}
