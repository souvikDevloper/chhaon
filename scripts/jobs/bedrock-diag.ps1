# Careful Bedrock diagnosis: account plan, quotas with non-zero values, model availability, and tiny test calls.
$ErrorActionPreference = 'Continue'
$env:AWS_PAGER = ''
function Section($t) { Write-Output ""; Write-Output "=== $t ===" }
$hello = 'scripts\fixtures\hello.json'

Section 'account plan (free tier API)'
aws freetier get-account-plan-state --region us-east-1 --output json 2>&1 | Select-Object -First 30

foreach ($r in 'ap-south-1', 'us-east-1') {
    Section "bedrock quotas in $r with a value above zero (first 40)"
    aws service-quotas list-service-quotas --service-code bedrock --region $r --query 'Quotas[?Value > `0`].[QuotaCode,Value,QuotaName]' --output text 2>&1 | Select-Object -First 40
    Section "bedrock quotas in ${r}, how many are zero vs total"
    $all = aws service-quotas list-service-quotas --service-code bedrock --region $r --query 'length(Quotas)' --output text 2>&1
    $zero = aws service-quotas list-service-quotas --service-code bedrock --region $r --query 'length(Quotas[?Value == `0`])' --output text 2>&1
    Write-Output "total=$all zero=$zero"
}

Section 'model availability for this account'
$checks = @(
    @('us-east-1', 'amazon.nova-2-lite-v1:0'), @('us-east-1', 'amazon.nova-lite-v1:0'), @('us-east-1', 'amazon.nova-micro-v1:0'),
    @('us-east-1', 'meta.llama3-8b-instruct-v1:0'), @('ap-south-1', 'amazon.nova-lite-v1:0'), @('ap-south-1', 'meta.llama3-8b-instruct-v1:0')
)
foreach ($c in $checks) {
    $out = aws bedrock get-foundation-model-availability --region $c[0] --model-id $c[1] --output json 2>&1 | Out-String
    Write-Output "$($c[0]) $($c[1]): $($out -replace '\s+', ' ')"
}

Section 'tiny converse calls (maxTokens 8)'
$tests = @(
    @('ap-south-1', 'global.amazon.nova-2-lite-v1:0'), @('ap-south-1', 'apac.amazon.nova-micro-v1:0'), @('ap-south-1', 'apac.amazon.nova-lite-v1:0'),
    @('ap-south-1', 'meta.llama3-8b-instruct-v1:0'), @('ap-south-1', 'mistral.mistral-7b-instruct-v0:2'),
    @('us-east-1', 'amazon.nova-micro-v1:0'), @('us-east-1', 'amazon.nova-lite-v1:0'), @('us-east-1', 'us.amazon.nova-micro-v1:0'),
    @('us-east-1', 'meta.llama3-8b-instruct-v1:0'), @('us-east-1', 'us.meta.llama3-1-8b-instruct-v1:0'),
    @('us-east-1', 'mistral.mistral-7b-instruct-v0:2'), @('us-east-1', 'openai.gpt-oss-20b-1:0'),
    @('us-west-2', 'us.amazon.nova-micro-v1:0'), @('us-west-2', 'openai.gpt-oss-20b-1:0')
)
foreach ($c in $tests) {
    $out = aws bedrock-runtime converse --region $c[0] --model-id $c[1] --messages "file://$hello" --inference-config maxTokens=8 --query 'output.message.content[0].text' --output text --cli-read-timeout 20 2>&1 | Out-String
    $line = ($out -replace '\s+', ' ').Trim()
    if ($line -match 'An error occurred \(([A-Za-z]+)\)[^:]*: (.{0,140})') { $line = "ERROR $($Matches[1]): $($Matches[2])" }
    Write-Output ("{0,-11} {1,-38} {2}" -f $c[0], $c[1], $line)
}
exit 0
