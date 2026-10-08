# Chhaon job runner (development helper).
# Start once from the repo root:   powershell -ExecutionPolicy Bypass -File scripts\runner.ps1
# It runs ONLY scripts that exist in scripts\jobs\, when a matching request file appears in
# scripts\queue\, and writes everything they print to scripts\logs\. Stop it any time with Ctrl+C.
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$queue = Join-Path $root 'scripts\queue'
$logs = Join-Path $root 'scripts\logs'
New-Item -ItemType Directory -Force -Path $queue, $logs | Out-Null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = 'utf-8'
$env:AWS_PAGER = ''
$env:AWS_CLI_FILE_ENCODING = 'UTF-8'
Write-Host "Chhaon runner watching $queue  (Ctrl+C to stop)" -ForegroundColor Green

while ($true) {
    Get-ChildItem -Path $queue -Filter '*.job' -ErrorAction SilentlyContinue | Sort-Object Name | ForEach-Object {
        $file = $_
        $id = $file.BaseName
        try { $req = Get-Content $file.FullName -Raw -Encoding UTF8 | ConvertFrom-Json } catch { $req = $null }
        Remove-Item $file.FullName -Force -ErrorAction SilentlyContinue
        $log = Join-Path $logs "$id.log"
        if (-not $req -or $req.job -notmatch '^[a-z0-9-]+$') { "### invalid request" | Out-File $log -Encoding utf8; return }
        $script = Join-Path $root "scripts\jobs\$($req.job).ps1"
        if (-not (Test-Path $script)) { "### unknown job $($req.job)" | Out-File $log -Encoding utf8; return }
        $argList = @()
        if ($req.args) { $req.args.PSObject.Properties | ForEach-Object { $argList += "-$($_.Name)"; $argList += "$($_.Value)" } }
        Write-Host ("[{0}] running {1} {2}" -f (Get-Date -Format HH:mm:ss), $req.job, ($argList -join ' ')) -ForegroundColor Cyan
        "### job $($req.job) started $(Get-Date -Format o)" | Out-File $log -Encoding utf8
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $script @argList 2>&1 | ForEach-Object {
            $line = "$_"
            Add-Content -Path $log -Value $line -Encoding UTF8
            Write-Host $line
        }
        $code = $LASTEXITCODE
        Add-Content -Path $log -Value "### EXIT $code $(Get-Date -Format o)" -Encoding UTF8
        Write-Host ("[{0}] {1} finished with exit code {2}" -f (Get-Date -Format HH:mm:ss), $req.job, $code) -ForegroundColor Cyan
    }
    Start-Sleep -Seconds 2
}
