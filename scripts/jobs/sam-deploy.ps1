# Validate (cfn-lint) and deploy the stack with the AWS SAM CLI, then publish the web app.
# The functions have no third-party dependencies (stdlib + boto3 from the Lambda runtime; Strands
# comes as a layer), so `sam deploy` zips each CodeUri as it is; no `sam build` step is needed.
param(
    [string]$Region = 'ap-south-1',
    [string]$Stack = 'chhaon',
    [string]$ModelId = 'global.amazon.nova-2-lite-v1:0',
    [string]$AlertEmail = '',
    [string]$StrandsLayerArn = ''
)
$ErrorActionPreference = 'Continue'
$env:AWS_PAGER = ''
$env:SAM_CLI_TELEMETRY = '0'
function Fail($msg) { Write-Output "DEPLOY FAILED: $msg"; exit 1 }
# (not named "sam": PowerShell would call the function itself instead of the CLI)
function Invoke-SamCli {
    $exe = Get-Command sam -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($exe) { & $exe.Source @args } else { & python -m samcli @args }
}

if (-not (Get-Command sam -CommandType Application -ErrorAction SilentlyContinue)) {
    python -c "import samcli" 2>$null
    if ($LASTEXITCODE -ne 0) { Write-Output 'installing the AWS SAM CLI'; python -m pip install aws-sam-cli --quiet 2>&1 | Select-Object -Last 2 }
}
Invoke-SamCli --version
$acct = aws sts get-caller-identity --query Account --output text
if ($LASTEXITCODE -ne 0) { Fail 'no AWS credentials' }
$bucket = "chhaon-artifacts-$acct-$Region"

Write-Output '--- sam validate --lint'
Invoke-SamCli validate --template-file infra\template.yaml --region $Region --lint 2>&1 | Select-Object -Last 25

Write-Output '--- sam deploy'
$params = @("ModelId=$ModelId")
if ($AlertEmail) { $params += "AlertEmail=$AlertEmail" }
if ($StrandsLayerArn) { $params += "StrandsLayerArn=$StrandsLayerArn" }
Invoke-SamCli deploy --template-file infra\template.yaml --stack-name $Stack --region $Region --s3-bucket $bucket --s3-prefix sam --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND --no-confirm-changeset --no-fail-on-empty-changeset --parameter-overrides @params 2>&1 | Select-Object -Last 30
if ($LASTEXITCODE -ne 0) { Fail 'sam deploy' }
& "$PSScriptRoot\web.ps1" -Region $Region -Stack $Stack
exit $LASTEXITCODE
