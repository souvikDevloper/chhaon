# Replace the latest commit's message with scripts\commit-message.txt and update GitHub.
$ErrorActionPreference = 'Continue'
$msgFile = 'scripts\commit-message.txt'
if (-not (Test-Path $msgFile)) { Write-Output 'no commit message file'; exit 1 }
git commit --amend --only -F $msgFile
Remove-Item $msgFile -Force
git push --force-with-lease origin main 2>&1
Write-Output '--- history (hash | author | committer | subject)'
git log --format='%h | %an <%ae> | %cn <%ce> | %s'
Write-Output '--- trailers left in any commit:'
git log --format=%B | Select-String -Pattern 'Co-Authored-By|Claude-Session' | ForEach-Object { $_.Line }
Write-Output '(none above means clean)'
exit 0
