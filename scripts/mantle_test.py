"""Probe the bedrock-mantle (OpenAI-compatible) endpoint with SigV4 using the local AWS credentials.

Prints status codes and short response snippets only; never prints credentials.
"""
import json
import sys
import urllib.error
import urllib.request

sys.path.insert(0, "build/pydeps")
import botocore.session  # noqa: E402
from botocore.auth import SigV4Auth  # noqa: E402
from botocore.awsrequest import AWSRequest  # noqa: E402

creds = botocore.session.get_session().get_credentials()


def call(method, url, region, service, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = AWSRequest(method=method, url=url, data=data, headers={"content-type": "application/json"})
    SigV4Auth(creds, service, region).add_auth(req)
    r = urllib.request.Request(req.url, data=data, headers=dict(req.headers.items()), method=method)
    try:
        with urllib.request.urlopen(r, timeout=25) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # network, DNS
        return 0, f"{type(e).__name__}: {e}"


for region in ("us-east-1", "us-west-2", "ap-south-1"):
    base = f"https://bedrock-mantle.{region}.api.aws/v1"
    print(f"=== {region} ===")
    service_ok = None
    models = []
    for service in ("bedrock-mantle", "bedrock"):
        code, text = call("GET", base + "/models", region, service)
        print(f"GET /models signed as {service}: {code} {text[:200]!r}")
        if code == 200:
            service_ok = service
            try:
                models = [m.get("id") for m in json.loads(text).get("data", [])]
            except Exception:
                models = []
            break
    if models:
        print(f"models ({len(models)}): {', '.join(sorted(models))[:900]}")
    if not service_ok:
        continue
    picks = [m for m in models if "nova" in m.lower()][:2] + [m for m in models if "gpt-oss-20b" in m][:1] + [m for m in models if "gpt-oss-120b" in m][:1]
    for model in picks or ["openai.gpt-oss-20b", "openai.gpt-oss-120b"]:
        body = {"model": model, "messages": [{"role": "user", "content": "Reply with the single word OK."}], "max_tokens": 16}
        code, text = call("POST", base + "/chat/completions", region, service_ok, body)
        snippet = text[:260].replace("\n", " ")
        print(f"chat {model}: {code} {snippet}")
