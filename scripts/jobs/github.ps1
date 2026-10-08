# Create the public GitHub repo on first run, then push.
$ErrorActionPreference = 'Continue'
$remote = git remote get-url origin 2>$null
if (-not $remote) {
    gh repo create chhaon --public --source . --remote origin --description "Heat-safe shifts for India's outdoor workers: WBGT planner, Hindi break announcements, heat-illness protocol. Built on AWS." --push 2>&1
} else {
    git push -u origin main 2>&1
}
git remote -v
gh repo view --json url,visibility --jq '.url + "  " + .visibility' 2>&1
exit 0
