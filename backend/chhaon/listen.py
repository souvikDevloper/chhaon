"""Amazon Transcribe streaming for spoken questions (Hindi or Indian English).

The phone streams microphone audio straight to Transcribe over a WebSocket; this
module only signs that WebSocket URL (SigV4 query signing with the function's role,
valid for 5 minutes, good for that one stream)."""
from __future__ import annotations

import os
from urllib.parse import urlencode

import boto3

SAMPLE_RATE = 16000


def presign(lang: str = "hi") -> dict:
    from botocore.auth import SigV4QueryAuth
    from botocore.awsrequest import AWSRequest

    region = os.environ.get("TRANSCRIBE_REGION") or os.environ.get("AWS_REGION", "ap-south-1")
    code = "en-IN" if lang == "en" else "hi-IN"
    query = urlencode({"language-code": code, "media-encoding": "pcm", "sample-rate": str(SAMPLE_RATE)})
    url = f"https://transcribestreaming.{region}.amazonaws.com:8443/stream-transcription-websocket?{query}"
    req = AWSRequest(method="GET", url=url)
    creds = boto3.Session().get_credentials().get_frozen_credentials()
    SigV4QueryAuth(creds, "transcribe", region, expires=300).add_auth(req)
    return {"url": "wss://" + req.url[len("https://"):], "sample_rate": SAMPLE_RATE, "language": code}
