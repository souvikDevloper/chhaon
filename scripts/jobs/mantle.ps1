# Check the bedrock-mantle endpoint: its own quotas, the models it offers, and a tiny chat request (SigV4, local credentials).
$ErrorActionPreference = 'Continue'
$env:AWS_PAGER = ''
foreach ($r in 'us-east-1', 'ap-south-1') {
    Write-Output "=== Mantle quotas in $r (applied values) ==="
    aws service-quotas list-service-quotas --service-code bedrock --region $r --query "Quotas[?contains(QuotaName,'antle')].[QuotaCode,Value,QuotaName]" --output text 2>&1 | Select-Object -First 25
}
python -c "import botocore" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Output 'installing botocore into build\pydeps (project folder only)'
    python -m pip install botocore --target build\pydeps --quiet 2>&1 | Select-Object -Last 2
}
python scripts\mantle_test.py 2>&1
exit 0
