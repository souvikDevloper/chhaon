# Bedrock daily token quotas (new accounts start low) and a Polly Hindi voice test.
param([string]$Region = 'ap-south-1', [string]$Request = '')
$ErrorActionPreference = 'Continue'
$env:AWS_PAGER = ''
Write-Output "=== bedrock quotas mentioning Nova ($Region) ==="
aws service-quotas list-service-quotas --service-code bedrock --region $Region --query "Quotas[?contains(QuotaName,'Nova')].[QuotaCode,Value,Adjustable,QuotaName]" --output text 2>&1 | Select-String -Pattern 'day|minute' | ForEach-Object { $_.Line }
Write-Output ""
Write-Output "=== defaults for comparison ==="
aws service-quotas list-aws-default-service-quotas --service-code bedrock --region $Region --query "Quotas[?contains(QuotaName,'Nova 2 Lite')].[QuotaCode,Value,QuotaName]" --output text 2>&1 | Select-String -Pattern 'day' | ForEach-Object { $_.Line }
if ($Request) {
    $code, $value = $Request -split '='
    Write-Output "=== requesting $code = $value ==="
    aws service-quotas request-service-quota-increase --service-code bedrock --quota-code $code --desired-value $value --region $Region --query "RequestedQuota.[Id,Status,QuotaName,DesiredValue]" --output text 2>&1
}
Write-Output ""
Write-Output "=== polly Kajal hi-IN neural ($Region) ==="
$out = Join-Path $env:TEMP 'chhaon-kajal.mp3'
aws polly synthesize-speech --region $Region --voice-id Kajal --engine neural --language-code hi-IN --output-format mp3 --text 'file://scripts\fixtures\hi.txt' $out 2>&1
if (Test-Path $out) { Write-Output "kajal mp3 bytes: $((Get-Item $out).Length)"; Remove-Item $out }
Write-Output "=== bedrock one-shot (global.amazon.nova-2-lite-v1:0) ==="
aws bedrock-runtime converse --region $Region --model-id global.amazon.nova-2-lite-v1:0 --messages 'file://scripts\fixtures\hello.json' --inference-config maxTokens=10 --query "output.message.content[0].text" --output text 2>&1
exit 0
