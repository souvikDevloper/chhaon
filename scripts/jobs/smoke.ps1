# End-to-end check of the live stack through CloudFront.
param([string]$Region = 'ap-south-1', [string]$Stack = 'chhaon', [switch]$Quick)
$ErrorActionPreference = 'Continue'
$env:AWS_PAGER = ''
$base = aws cloudformation describe-stacks --region $Region --stack-name $Stack --query "Stacks[0].Outputs[?OutputKey=='SiteUrl'].OutputValue" --output text
Write-Output "BASE $base"
$utf8 = [System.Text.Encoding]::UTF8
function Call($method, $path, $body) {
    $uri = "$base/api$path"
    try {
        if ($body -ne $null) {
            $json = $body | ConvertTo-Json -Depth 6 -Compress
            $r = Invoke-WebRequest -UseBasicParsing -Method $method -Uri $uri -Body $utf8.GetBytes($json) -ContentType 'application/json; charset=utf-8' -TimeoutSec 40
        } else {
            $r = Invoke-WebRequest -UseBasicParsing -Method $method -Uri $uri -TimeoutSec 40
        }
        $text = $utf8.GetString($r.RawContentStream.ToArray())
        return @{ code = [int]$r.StatusCode; data = ($text | ConvertFrom-Json); raw = $text }
    } catch {
        $resp = $_.Exception.Response
        $code = if ($resp) { [int]$resp.StatusCode } else { 0 }
        $msg = $_.ErrorDetails.Message
        return @{ code = $code; data = $null; raw = "$msg $($_.Exception.Message)" }
    }
}
function Show($label, $r, [int]$n = 400) { $s = $r.raw; if ($s.Length -gt $n) { $s = $s.Substring(0, $n) + '...' }; Write-Output "[$($r.code)] $label :: $s" }

$r = Call GET '/health' $null; Show 'health' $r
$page = Invoke-WebRequest -UseBasicParsing -Uri "$base/" -TimeoutSec 30; Write-Output "[$($page.StatusCode)] index.html $($page.RawContentLength) bytes"
$r = Call POST '/demo' @{}; Show 'demo' $r; $sid = $r.data.site_id
$r = Call GET "/sites/$sid/plan?day=today" $null
Write-Output "[$($r.code)] plan today: verdict=$($r.data.plan.verdict) stops=$($r.data.plan.crew.stop_windows | ConvertTo-Json -Compress) unsafe=$($r.data.plan.unsafe_hours_normal) avoided=$($r.data.plan.unsafe_hours_avoided) peak=$($r.data.plan.peak_wbgt)@$($r.data.plan.peak_time) events=$($r.data.plan.events.Count)"
$r = Call GET "/sites/$sid/plan?day=tomorrow" $null
Write-Output "[$($r.code)] plan tomorrow: verdict=$($r.data.plan.verdict) stops=$($r.data.plan.crew.stop_windows | ConvertTo-Json -Compress) first=$($r.data.plan.crew.first_start) last=$($r.data.plan.crew.last_end) kept=$($r.data.plan.crew.planned_minutes)/$($r.data.plan.crew.target_minutes)"
$r = Call POST "/sites/$sid/publish" @{ day = 'tomorrow' }; Show 'publish tomorrow' $r
$r = Call POST "/sites/$sid/preview" @{ kind = 'pause'; until = '16:00'; lang = 'hi' }; Show 'preview (polly)' $r
if ($r.data.audio) { $a = Invoke-WebRequest -UseBasicParsing -Uri "$base$($r.data.audio)" -TimeoutSec 30; Write-Output "[$($a.StatusCode)] audio $($a.RawContentLength) bytes $($a.Headers['Content-Type'])" }
$r = Call GET '/geocode?q=Salt%20Lake%20Sector%20V%20Kolkata' $null; Show 'geocode' $r 300
$r = Call GET '/replays' $null; Show 'replays' $r 300
$r = Call GET '/replay/aurangabad-2024-05-30' $null
Write-Output "[$($r.code)] replay aurangabad: stops=$($r.data.plan.crew.stop_windows | ConvertTo-Json -Compress) peak=$($r.data.plan.peak_wbgt)@$($r.data.plan.peak_time)"
$q = [System.IO.File]::ReadAllText((Join-Path (Get-Location) 'scripts\fixtures\ask-hi.txt'), $utf8)
$r = Call POST '/ask' @{ site_id = $sid; question = $q }; Show 'ask (hi)' $r 600
$r = Call POST '/ask' @{ site_id = $sid; question = 'When does heavy work stop today?' }; Show 'ask (en)' $r 600
$r = Call POST "/sites/$sid/test-announcement" @{}; Show 'test-announcement' $r

$r = Call POST "/sites/$sid/incidents" @{ symptoms = @('dizzy', 'vomiting'); worker = 'Ramesh'; lang = 'en' }
$iid = $r.data.id; Write-Output "[$($r.code)] incident $iid level=$($r.data.level)"
$asked = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 3
    $r = Call GET "/incidents/$iid" $null
    if ($r.data.pending -and $r.data.pending.question -eq 'recheck') { $asked = $true; break }
}
Write-Output "recheck asked: $asked after $((($i + 1) * 3))s; status=$($r.data.status)"
if ($asked) {
    $a = Call POST "/incidents/$iid/answer" @{ answer = 'worse' }; Show 'answer worse' $a
    for ($j = 0; $j -lt 15; $j++) { Start-Sleep -Seconds 2; $r = Call GET "/incidents/$iid" $null; if ($r.data.status -eq 'emergency' -and $r.data.pending) { break } }
    Write-Output "after worse: status=$($r.data.status) level=$($r.data.level) hospitals=$(($r.data.hospitals | ForEach-Object { $_.name + ' ' + [math]::Round($_.distance_m) + 'm' }) -join '; ') pending=$($r.data.pending.question)"
    $a = Call POST "/incidents/$iid/answer" @{ answer = 'handed_over' }; Show 'answer handed_over' $a
    Start-Sleep -Seconds 4
    $r = Call GET "/incidents/$iid" $null
    Write-Output "final: status=$($r.data.status)"
    $r.data.timeline | ForEach-Object { Write-Output ("  {0} {1}: {2}" -f $_.t, $_.kind, $_.text) }
}

if (-not $Quick) {
    Write-Output 'waiting for the scheduled test announcement...'
    for ($k = 0; $k -lt 20; $k++) {
        Start-Sleep -Seconds 6
        $r = Call GET "/sites/$sid/feed" $null
        $ann = $r.data.items | Where-Object { $_.type -eq 'announcement' }
        if ($ann) { break }
    }
    if ($ann) { Write-Output "ANNOUNCEMENT ARRIVED: $($ann[-1].ts) kind=$($ann[-1].kind) audio=$($ann[-1].audio | ConvertTo-Json -Compress)" } else { Write-Output 'no announcement yet' }
}
Write-Output "SITE: $base"
exit 0
