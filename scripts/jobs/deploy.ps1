# Package and deploy the stack with the AWS CLI (no SAM CLI needed), then publish the web app.
param(
    [string]$Region = 'ap-south-1',
    [string]$Stack = 'chhaon',
    [string]$ModelId = 'apac.amazon.nova-2-lite-v1:0',
    [string]$AlertEmail = '',
    [string]$StrandsLayerArn = ''
)
$ErrorActionPreference = 'Continue'
$env:AWS_PAGER = ''
function Fail($msg) { Write-Output "DEPLOY FAILED: $msg"; exit 1 }

$acct = aws sts get-caller-identity --query Account --output text
if ($LASTEXITCODE -ne 0) { Fail 'no AWS credentials' }
$bucket = "chhaon-artifacts-$acct-$Region"
aws s3api head-bucket --bucket $bucket 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Output "creating artifacts bucket $bucket"
    if ($Region -eq 'us-east-1') { aws s3api create-bucket --bucket $bucket --region $Region | Out-Null }
    else { aws s3api create-bucket --bucket $bucket --region $Region --create-bucket-configuration LocationConstraint=$Region | Out-Null }
    if ($LASTEXITCODE -ne 0) { Fail 'could not create artifacts bucket' }
    aws s3api put-public-access-block --bucket $bucket --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
}

New-Item -ItemType Directory -Force -Path build | Out-Null
Write-Output '--- package'
aws cloudformation package --region $Region --template-file infra\template.yaml --s3-bucket $bucket --s3-prefix pkg --output-template-file build\packaged.yaml
if ($LASTEXITCODE -ne 0) { Fail 'package' }

Write-Output '--- deploy (CloudFront can take 3-6 minutes the first time)'
$params = @("ModelId=$ModelId")
if ($AlertEmail) { $params += "AlertEmail=$AlertEmail" }
if ($StrandsLayerArn) { $params += "StrandsLayerArn=$StrandsLayerArn" }
aws cloudformation deploy --region $Region --template-file build\packaged.yaml --stack-name $Stack --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND --no-fail-on-empty-changeset --parameter-overrides @params
$deployCode = $LASTEXITCODE
if ($deployCode -ne 0) {
    Write-Output '--- failed events'
    aws cloudformation describe-stack-events --region $Region --stack-name $Stack --max-items 40 --query "StackEvents[?contains(ResourceStatus,'FAILED')].[Timestamp,LogicalResourceId,ResourceStatusReason]" --output text
    Fail 'cloudformation deploy'
}

Write-Output '--- outputs'
aws cloudformation describe-stacks --region $Region --stack-name $Stack --query "Stacks[0].Outputs" --output json | Out-File -Encoding ascii build\outputs.json
Get-Content build\outputs.json
& "$PSScriptRoot\web.ps1" -Region $Region -Stack $Stack
exit $LASTEXITCODE
