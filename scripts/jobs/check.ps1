# Readiness check: tools, identity, and whether each AWS service Chhaon needs works in each candidate region.
$ErrorActionPreference = 'Continue'
$env:AWS_PAGER = ''
function Section($t) { Write-Output ""; Write-Output "=== $t ===" }

Section 'tools'
aws --version 2>&1
git --version 2>&1
python --version 2>&1
python -m pip --version 2>&1
foreach ($t in 'sam', 'gh') { $c = Get-Command $t -ErrorAction SilentlyContinue; Write-Output "${t}: $(if ($c) { $c.Source } else { 'missing' })" }

Section 'identity'
aws sts get-caller-identity --output json 2>&1
Write-Output "default region: $(aws configure get region 2>&1)"
Write-Output "git user: $(git config --global user.name 2>&1) <$(git config --global user.email 2>&1)>"
if (Get-Command gh -ErrorAction SilentlyContinue) { gh auth status 2>&1 }

$hello = 'scripts\fixtures\hello.json'
foreach ($r in 'ap-south-1', 'us-east-1') {
    Section "bedrock $r"
    aws bedrock list-inference-profiles --region $r --query "inferenceProfileSummaries[?contains(inferenceProfileId,'nova')].inferenceProfileId" --output text 2>&1
    $models = if ($r -eq 'us-east-1') { 'us.amazon.nova-2-lite-v1:0', 'global.amazon.nova-2-lite-v1:0', 'us.amazon.nova-lite-v1:0' } else { 'apac.amazon.nova-2-lite-v1:0', 'global.amazon.nova-2-lite-v1:0', 'apac.amazon.nova-lite-v1:0' }
    foreach ($m in $models) {
        $out = aws bedrock-runtime converse --region $r --model-id $m --messages "file://$hello" --inference-config maxTokens=20 --query "output.message.content[0].text" --output text 2>&1
        Write-Output "converse ${m}: $out"
    }
    Section "polly $r"
    aws polly synthesize-speech --region $r --voice-id Kajal --engine neural --language-code hi-IN --output-format mp3 --text 'file://scripts\fixtures\hi.txt' "$env:TEMP\chhaon-kajal.mp3" 2>&1
    if (Test-Path "$env:TEMP\chhaon-kajal.mp3") { Write-Output "kajal mp3 bytes: $((Get-Item "$env:TEMP\chhaon-kajal.mp3").Length)"; Remove-Item "$env:TEMP\chhaon-kajal.mp3" }
    Section "location $r"
    aws geo-places search-nearby --region $r --query-position 88.2636 22.5958 --query-radius 15000 --filter IncludeCategories=hospital --max-results 3 --query "ResultItems[].[Title,Distance]" --output text 2>&1
    Section "scheduler $r"
    aws scheduler list-schedule-groups --region $r --query "ScheduleGroups[].Name" --output text 2>&1
    Section "stepfunctions $r"
    aws stepfunctions list-state-machines --region $r --max-results 1 --query "length(stateMachines)" 2>&1
}

Section 'cloudfront'
aws cloudfront list-distributions --query "DistributionList.Quantity" 2>&1
Section 'stacks'
aws cloudformation list-stacks --region ap-south-1 --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE ROLLBACK_COMPLETE --query "StackSummaries[].StackName" --output text 2>&1
aws cloudformation list-stacks --region us-east-1 --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE ROLLBACK_COMPLETE --query "StackSummaries[].StackName" --output text 2>&1

Section 'weather fixtures'
New-Item -ItemType Directory -Force -Path 'data\fixtures' | Out-Null
$hourly = 'temperature_2m,relative_humidity_2m,wind_speed_10m,shortwave_radiation,direct_radiation,diffuse_radiation,surface_pressure'
$targets = @(
    @{ name = 'forecast-howrah'; url = "https://api.open-meteo.com/v1/forecast?latitude=22.5958&longitude=88.2636&hourly=$hourly,wet_bulb_temperature_2m&wind_speed_unit=ms&timezone=Asia/Kolkata&forecast_days=3&past_days=1" },
    @{ name = 'archive-rourkela-2024-05-30'; url = "https://archive-api.open-meteo.com/v1/archive?latitude=22.2604&longitude=84.8536&hourly=$hourly&wind_speed_unit=ms&timezone=Asia/Kolkata&start_date=2024-05-30&end_date=2024-05-31" },
    @{ name = 'archive-aurangabad-2024-05-30'; url = "https://archive-api.open-meteo.com/v1/archive?latitude=24.7522&longitude=84.374&hourly=$hourly&wind_speed_unit=ms&timezone=Asia/Kolkata&start_date=2024-05-30&end_date=2024-05-31" },
    @{ name = 'archive-howrah-2025-10-08'; url = "https://archive-api.open-meteo.com/v1/archive?latitude=22.5958&longitude=88.2636&hourly=$hourly&wind_speed_unit=ms&timezone=Asia/Kolkata&start_date=2025-10-08&end_date=2025-10-09" }
)
foreach ($t in $targets) {
    try {
        $resp = Invoke-WebRequest -UseBasicParsing -Uri $t.url -TimeoutSec 30
        [System.IO.File]::WriteAllText((Join-Path (Get-Location) "data\fixtures\$($t.name).json"), $resp.Content)
        Write-Output "$($t.name): saved $($resp.Content.Length) bytes"
    } catch { Write-Output "$($t.name): FAILED $($_.Exception.Message)" }
}
exit 0
