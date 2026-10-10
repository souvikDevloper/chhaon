# Stop tracking helper scripts that don't belong in the public repo (the files stay on disk, ignored).
$ErrorActionPreference = 'Continue'
git rm --cached --ignore-unmatch scripts/jobs/fix-attribution.ps1 scripts/jobs/amend-message.ps1 2>&1
git status --short
exit 0
