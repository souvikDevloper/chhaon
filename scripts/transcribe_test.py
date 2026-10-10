"""End-to-end check of spoken questions without a microphone: Polly says a Hindi question as
16 kHz PCM, we stream it to Amazon Transcribe through the same presigned WebSocket URL the
phone uses (backend/chhaon/listen.py), framed in AWS event-stream format, and print the text."""
import asyncio
import json
import os
import struct
import sys
import zlib

sys.path.insert(0, "build/winpy")
sys.path.insert(0, "backend")
os.environ.setdefault("AWS_REGION", "ap-south-1")

import boto3  # noqa: E402
import websockets  # noqa: E402

from chhaon import listen  # noqa: E402

QUESTION = open("scripts/fixtures/ask-hi.txt", encoding="utf-8").read().strip()


def header(name: str, value: str) -> bytes:
    n, v = name.encode(), value.encode()
    return bytes([len(n)]) + n + bytes([7]) + struct.pack(">H", len(v)) + v


def frame(payload: bytes) -> bytes:
    headers = header(":content-type", "application/octet-stream") + header(":event-type", "AudioEvent") + header(":message-type", "event")
    total = 12 + len(headers) + len(payload) + 4
    prelude = struct.pack(">II", total, len(headers))
    msg = prelude + struct.pack(">I", zlib.crc32(prelude)) + headers + payload
    return msg + struct.pack(">I", zlib.crc32(msg))


def parse(data: bytes):
    total, hlen = struct.unpack(">II", data[:8])
    headers, o = {}, 12
    while o < 12 + hlen:
        n = data[o]; name = data[o + 1:o + 1 + n].decode(); o += 1 + n
        t = data[o]; o += 1
        if t != 7:
            break
        vl = struct.unpack(">H", data[o:o + 2])[0]; headers[name] = data[o + 2:o + 2 + vl].decode(); o += 2 + vl
    return headers, data[12 + hlen:total - 4].decode("utf-8", "replace")


async def main():
    pcm = boto3.client("polly", region_name="ap-south-1").synthesize_speech(
        Text=QUESTION, VoiceId="Kajal", Engine="neural", LanguageCode="hi-IN", OutputFormat="pcm", SampleRate="16000")["AudioStream"].read()
    if len(sys.argv) > 1:  # sign through the live API (the Lambda's role), as the phone does
        import urllib.request
        req = urllib.request.Request(sys.argv[1].rstrip("/") + "/api/listen", data=b'{"lang":"hi"}', headers={"content-type": "application/json"}, method="POST")
        signed = json.loads(urllib.request.urlopen(req, timeout=20).read())
    else:
        signed = listen.presign("hi")
    print("signed url host:", signed["url"].split("/")[2], "| audio bytes:", len(pcm))
    finals = []
    async with websockets.connect(signed["url"], max_size=None) as ws:
        async def send():
            chunk = 3200  # 100 ms of 16-bit mono at 16 kHz
            for i in range(0, len(pcm), chunk):
                await ws.send(frame(pcm[i:i + chunk]))
                await asyncio.sleep(0.1)
            await ws.send(frame(b"\0\0" * 16000))  # a second of silence
            await asyncio.sleep(1.0)
            await ws.send(frame(b""))
        sender = asyncio.create_task(send())
        try:
            async for msg in ws:
                headers, body = parse(msg)
                if headers.get(":message-type") != "event":
                    print("ERROR", headers, body)
                    break
                for r in json.loads(body).get("Transcript", {}).get("Results", []):
                    if not r.get("IsPartial"):
                        finals.append(r["Alternatives"][0]["Transcript"])
        except websockets.ConnectionClosed:
            pass
        await sender
    print("asked:      ", QUESTION)
    print("transcribed:", " ".join(finals))


asyncio.run(main())
