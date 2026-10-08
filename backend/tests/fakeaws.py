"""In-memory stand-ins for the boto3 calls Chhaon makes, so the handlers can be
exercised end to end without AWS (and without boto3 installed)."""
from __future__ import annotations

import io
import sys
import types


class ClientError(Exception):
    def __init__(self, code="Error", msg=""):
        super().__init__(msg or code)
        self.response = {"Error": {"Code": code, "Message": msg}}


class _Cond:
    def __init__(self, fn):
        self.fn = fn

    def __and__(self, other):
        return _Cond(lambda item: self.fn(item) and other.fn(item))


class Key:
    def __init__(self, name):
        self.name = name

    def eq(self, v):
        return _Cond(lambda i: i.get(self.name) == v)

    def begins_with(self, v):
        return _Cond(lambda i: str(i.get(self.name, "")).startswith(v))

    def gt(self, v):
        return _Cond(lambda i: str(i.get(self.name, "")) > v)


class ConditionalCheckFailedException(Exception):
    pass


class FakeTable:
    def __init__(self):
        self.items: dict[tuple, dict] = {}
        self.meta = types.SimpleNamespace(client=types.SimpleNamespace(exceptions=types.SimpleNamespace(ConditionalCheckFailedException=ConditionalCheckFailedException)))

    def put_item(self, Item, ConditionExpression=None, ExpressionAttributeNames=None, ExpressionAttributeValues=None):
        key = (Item["PK"], Item["SK"])
        if ConditionExpression == "#v = :v":
            cur = self.items.get(key, {})
            if cur.get("v", 0) != ExpressionAttributeValues[":v"]:
                raise ConditionalCheckFailedException()
        self.items[key] = dict(Item)

    def get_item(self, Key, ConsistentRead=False):
        item = self.items.get((Key["PK"], Key["SK"]))
        return {"Item": dict(item)} if item else {}

    def query(self, KeyConditionExpression, ScanIndexForward=True, Limit=None, ExclusiveStartKey=None):
        rows = [dict(v) for v in self.items.values() if KeyConditionExpression.fn(v)]
        rows.sort(key=lambda r: r["SK"], reverse=not ScanIndexForward)
        if Limit:
            rows = rows[:Limit]
        return {"Items": rows}

    def update_item(self, Key, UpdateExpression, ExpressionAttributeNames=None, ExpressionAttributeValues=None, ReturnValues=None):
        k = (Key["PK"], Key["SK"])
        item = self.items.setdefault(k, {"PK": Key["PK"], "SK": Key["SK"]})
        item["n"] = item.get("n", 0) + ExpressionAttributeValues[":one"]
        return {"Attributes": {"n": item["n"]}}


class FakeClient:
    def __init__(self, name, world):
        self.name = name
        self.world = world
        self.exceptions = types.SimpleNamespace(ConflictException=ClientError)

    # s3
    def head_object(self, Bucket, Key):
        if Key not in self.world.s3:
            raise ClientError("404")
        return {}

    def put_object(self, Bucket, Key, Body, **kw):
        self.world.s3[Key] = Body

    # polly
    def synthesize_speech(self, **kw):
        self.world.polly.append(kw)
        return {"AudioStream": io.BytesIO(b"ID3fake")}

    # scheduler
    def create_schedule(self, **kw):
        if kw["Name"] in self.world.schedules:
            raise ClientError("ConflictException")
        self.world.schedules[kw["Name"]] = kw

    def delete_schedule(self, Name, GroupName):
        if Name not in self.world.schedules:
            raise ClientError("ResourceNotFoundException")
        del self.world.schedules[Name]

    # step functions
    def start_execution(self, stateMachineArn, name, input):
        self.world.executions.append({"name": name, "input": input})
        return {"executionArn": f"arn:aws:states:local:execution:{name}"}

    def send_task_success(self, taskToken, output):
        self.world.task_success.append({"token": taskToken, "output": output})

    # geo-places
    def search_nearby(self, **kw):
        return {"ResultItems": [{"Title": "District Hospital", "Address": {"Label": "Main Rd"}, "Position": [88.27, 22.59], "Distance": 1800}]}

    def search_text(self, **kw):
        return {"ResultItems": []}

    def geocode(self, **kw):
        return {"ResultItems": [{"Title": "Howrah", "Address": {"Label": "Howrah, West Bengal"}, "Position": [88.26, 22.59]}]}

    # sns
    def publish(self, **kw):
        self.world.sns.append(kw)

    # bedrock
    def converse(self, **kw):
        raise ClientError("AccessDeniedException", "no model access in tests")


class World:
    def __init__(self):
        self.table = FakeTable()
        self.s3, self.schedules, self.sns = {}, {}, []
        self.polly, self.executions, self.task_success = [], [], []


def install() -> World:
    world = World()
    boto3 = types.ModuleType("boto3")
    boto3.resource = lambda name, **kw: types.SimpleNamespace(Table=lambda n: world.table)
    boto3.client = lambda name, **kw: FakeClient(name, world)
    dyn = types.ModuleType("boto3.dynamodb")
    cond = types.ModuleType("boto3.dynamodb.conditions")
    cond.Key = Key
    botocore = types.ModuleType("botocore")
    exc = types.ModuleType("botocore.exceptions")
    exc.ClientError = ClientError
    exc.BotoCoreError = type("BotoCoreError", (Exception,), {})
    sys.modules.update({"boto3": boto3, "boto3.dynamodb": dyn, "boto3.dynamodb.conditions": cond, "botocore": botocore, "botocore.exceptions": exc})
    return world
