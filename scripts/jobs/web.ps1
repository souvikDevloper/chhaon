# Publish web/ to the site bucket and refresh CloudFront.
param([string]$Region = 'ap-south-1', [string]$Stack = 'chhaon')
$ErrorActionPreference = 'Continue'
$env:AWS_PAGER = ''
$outs = aws cloudformation describe-stacks --region $Region --stack-name $Stack --query "Stacks[0].Outputs" --output json | ConvertFrom-Json
if (-not $outs) { Write-Output 'stack outputs not found'; exit 1 }
$get = { param($k) ($outs | Where-Object { $_.OutputKey -eq $k }).OutputValue }
$bucket = & $get 'WebBucketName'
$dist = & $get 'DistributionId'
$url = & $get 'SiteUrl'
Write-Output "--- sync web -> s3://$bucket"
aws s3 sync web "s3://$bucket" --region $Region --delete --exclude 'audio/*' --exclude '*.html' --cache-control 'public, max-age=300'
aws s3 sync web "s3://$bucket" --region $Region --exclude '*' --include '*.html' --cache-control 'no-cache' --content-type 'text/html; charset=utf-8'
if ($LASTEXITCODE -ne 0) { Write-Output 'sync failed'; exit 1 }
aws cloudfront create-invalidation --distribution-id $dist --paths '/*' --query 'Invalidation.Id' --output text
Write-Output "SITE: $url"
exit 0
