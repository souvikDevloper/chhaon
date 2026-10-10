# Build the Strands Agents SDK as an arm64 Lambda layer for Python 3.12 and publish it.
param([string]$Region = 'ap-south-1')
$ErrorActionPreference = 'Continue'
$env:AWS_PAGER = ''
$acct = aws sts get-caller-identity --query Account --output text
$bucket = "chhaon-artifacts-$acct-$Region"
Remove-Item -Recurse -Force build\layer -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path build\layer\python | Out-Null
# uv resolves for the target (Linux arm64), not for this Windows PC: plain pip evaluates
# "sys_platform == win32" markers for the host and falls back to an old Strands release.
python -m pip install uv --quiet --upgrade 2>&1 | Select-Object -Last 1
python -m uv pip install "strands-agents[openai]" --target build\layer\python --python-platform aarch64-manylinux2014 --python-version 3.12 --only-binary :all: 2>&1 | Select-Object -Last 5
if ($LASTEXITCODE -ne 0) { Write-Output 'install failed'; exit 1 }
Get-ChildItem build\layer\python -Filter 'strands_agents-*.dist-info' | ForEach-Object { Write-Output "packaged: $($_.Name)" }
Push-Location build\layer
python -m zipfile -c ..\strands-layer.zip python
Pop-Location
Write-Output "layer zip bytes: $((Get-Item build\strands-layer.zip).Length)"
aws s3 cp build\strands-layer.zip "s3://$bucket/layers/strands-layer.zip" --region $Region --only-show-errors
aws lambda publish-layer-version --region $Region --layer-name chhaon-strands --description 'Strands Agents SDK with the OpenAI-compatible provider' --content "S3Bucket=$bucket,S3Key=layers/strands-layer.zip" --compatible-runtimes python3.12 --compatible-architectures arm64 --query LayerVersionArn --output text
exit $LASTEXITCODE
