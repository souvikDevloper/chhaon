param([string]$Base = '')
# Stream a Polly-spoken Hindi question to Amazon Transcribe through the presigned WebSocket (no microphone needed).
$ErrorActionPreference = 'Continue'
python -m pip install websockets --target build\winpy --upgrade --quiet 2>&1 | Select-Object -Last 2
python scripts\transcribe_test.py $Base 2>&1
exit 0
