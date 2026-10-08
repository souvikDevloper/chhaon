"""Amazon Polly announcements, cached in S3 so a repeated sentence is synthesised once.

Kajal (neural) speaks both Hindi and Indian English; Aditi (standard) is the fallback.
Audio is served by CloudFront at /audio/<sha>.mp3.
"""
from __future__ import annotations

import hashlib
import os

import boto3
from botocore.exceptions import ClientError

_polly = None
_s3 = None


def _clients():
    global _polly, _s3
    if _polly is None:
        _polly = boto3.client("polly")
        _s3 = boto3.client("s3")
    return _polly, _s3


def speak(text: str, lang: str) -> str:
    """Return the site-relative URL of an MP3 for `text`."""
    polly, s3 = _clients()
    bucket = os.environ["WEB_BUCKET"]
    code = "hi-IN" if lang == "hi" else "en-IN"
    digest = hashlib.sha256(f"{code}|{text}".encode()).hexdigest()[:32]
    key = f"audio/{digest}.mp3"
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return "/" + key
    except ClientError:
        pass
    try:
        audio = polly.synthesize_speech(
            Text=text, VoiceId="Kajal", Engine="neural", LanguageCode=code, OutputFormat="mp3"
        )
    except ClientError:
        audio = polly.synthesize_speech(
            Text=text, VoiceId="Aditi", Engine="standard", LanguageCode=code, OutputFormat="mp3"
        )
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=audio["AudioStream"].read(),
        ContentType="audio/mpeg",
        CacheControl="public, max-age=31536000, immutable",
    )
    return "/" + key
