"""测试 LLMClient 的真实流式解析（用 httpx2 MockTransport 注入真实 openai SDK）。"""

import asyncio
import json
import sys

sys.path.insert(0, ".")

import httpx2
from openai import AsyncOpenAI

from agent.llm import LLMClient
from agent.messages import Message

PASS = 0
FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok: {name}")
    else:
        FAIL += 1
        print(f"  FAIL: {name}")


def make_chunk(content=None, tool_calls=None, finish=None, delta_extra=None):
    data = {
        "id": "1",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": "m",
        "choices": [{"index": 0, "delta": {}, "finish_reason": None}],
    }
    if content is not None:
        data["choices"][0]["delta"]["content"] = content
    if tool_calls:
        data["choices"][0]["delta"]["tool_calls"] = tool_calls
    if delta_extra:
        data["choices"][0]["delta"].update(delta_extra)
    if finish:
        data["choices"][0]["finish_reason"] = finish
    return data


def build_stream_handler(chunks):
    async def handler(request):
        body = b"".join(f"data: {json.dumps(c)}\n\n".encode() for c in chunks)
        return httpx2.Response(
            200, content=body, headers={"Content-Type": "text/event-stream"}
        )

    return handler


async def test_text_stream():
    chunks = [
        make_chunk(content="Hello"),
        make_chunk(content=" world"),
        make_chunk(finish="stop"),
    ]
    transport = httpx2.MockTransport(build_stream_handler(chunks))
    http_client = httpx2.AsyncClient(transport=transport)
    client = LLMClient(model="m", base_url="http://test", api_key="k", client=None)
    client._client = AsyncOpenAI(
        base_url="http://test", api_key="k", http_client=http_client
    )
    resp = await client.complete([Message(role="user", content="hi")])
    check("text_content", resp.content == "Hello world")
    check("text_finish", resp.finish_reason == "stop")


async def test_tool_call_stream():
    # 分片 tool_calls
    chunks = [
        make_chunk(
            tool_calls=[
                {
                    "index": 0,
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "Write", "arguments": ""},
                }
            ]
        ),
        make_chunk(tool_calls=[{"index": 0, "function": {"arguments": '{"file_'}}]),
        make_chunk(
            tool_calls=[
                {"index": 0, "function": {"arguments": 'path":"a.txt","content":"hi"}'}}
            ]
        ),
        make_chunk(finish="tool_calls"),
    ]
    transport = httpx2.MockTransport(build_stream_handler(chunks))
    http_client = httpx2.AsyncClient(transport=transport)
    client = LLMClient(model="m", base_url="http://test", api_key="k", client=None)
    client._client = AsyncOpenAI(
        base_url="http://test", api_key="k", http_client=http_client
    )
    resp = await client.complete([Message(role="user", content="hi")])
    check("tool_count", len(resp.tool_calls) == 1)
    check("tool_name", resp.tool_calls[0].name == "Write")
    check(
        "tool_args",
        resp.tool_calls[0].arguments == {"file_path": "a.txt", "content": "hi"},
    )
    check("tool_finish", resp.finish_reason == "tool_calls")


async def main():
    await test_text_stream()
    await test_tool_call_stream()
    print(f"\n{PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
