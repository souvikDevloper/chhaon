# Build the Strands Agents SDK as an arm64 Lambda layer for Python 3.12 and publish it.
param([string]$Region = 'ap-south-1')
$ErrorActionPreference = 'Continue'
$env:AWS_PAGER = ''
$acct = aws sts get-caller-identity --query Account --output text
$bucket = "chhaon-artifacts-$acct-$Region"
Remove-Item -Recurse -Force build\layer -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path build\layer\python | Out-Null
python -m pip install strands-agents --target build\layer\python --platform manylinux2014_aarch64 --implementation cp --python-version 3.12 --only-binary=:all: --upgrade --quiet
if ($LASTEXITCODE -ne 0) { Write-Output 'pip failed'; exit 1 }
Push-Location build\layer
python -m zipfile -c ..\strands-layer.zip python
Pop-Location
Write-Output "layer zip bytes: $((Get-Item build\strands-layer.zip).Length)"
aws s3 cp build\strands-layer.zip "s3://$bucket/layers/strands-layer.zip" --region $Region --only-show-errors
aws lambda publish-layer-version --region $Region --layer-name chhaon-strands --description 'Strands Agents SDK' --content "S3Bucket=$bucket,S3Key=layers/strands-layer.zip" --compatible-runtimes python3.12 --compatible-architectures arm64 --query LayerVersionArn --output text
exit $LASTEXITCODE
