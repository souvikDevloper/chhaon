# Remove co-author trailers from the latest commit message (author stays the repo owner) and update GitHub.
$ErrorActionPreference = 'Continue'
$lines = git log -1 --format=%B
$clean = $lines | Where-Object { $_ -notmatch '^(Co-Authored-By|Claude-Session):' }
$tmp = Join-Path $env:TEMP 'chhaon-msg.txt'
[System.IO.File]::WriteAllText($tmp, (($clean -join "`n").TrimEnd() + "`n"))
git commit --amend --only -F $tmp
Remove-Item $tmp
git push --force-with-lease origin main 2>&1
Write-Output '--- history (hash | author | committer | subject)'
git log --format='%h | %an <%ae> | %cn <%ce> | %s'
Write-Output '--- trailers left:'
git log --format=%B | Select-String -Pattern 'Co-Authored-By|Claude-Session' | ForEach-Object { $_.Line }
Write-Output '(none above means clean)'
exit 0
