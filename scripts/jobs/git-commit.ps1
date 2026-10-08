# Commit everything with the message in scripts\commit-message.txt (initialises the repo on first run).
$ErrorActionPreference = 'Continue'
if (-not (Test-Path .git)) { git init -b main }
$msgFile = 'scripts\commit-message.txt'
if (-not (Test-Path $msgFile)) { Write-Output 'no commit message file'; exit 1 }
git add -A
git -c core.autocrlf=false commit -F $msgFile
Remove-Item $msgFile -Force
git log --oneline -n 5
exit 0
