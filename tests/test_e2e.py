"""端到端：真实 openai SDK + MockTransport 走完整 run() 循环。"""

import asyncio
import json
import sys
import tempfile

sys.path.insert(0, ".")

import httpx2
from openai import AsyncOpenAI

from agent import Agent, PermissionRule
from agent.llm import LLMClient

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


def make_chunk(content=None, tool_calls=None, finish=None):
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
    if finish:
        data["choices"][0]["finish_reason"] = finish
    return data


def build_handler(sequences):
    """按请求序号返回不同的 chunk 序列。"""
    state = {"i": 0}

    async def handler(request):
        idx = min(state["i"], len(sequences) - 1)
        state["i"] += 1
        chunks = sequences[idx]
        body = b"".join(f"data: {json.dumps(c)}\n\n".encode() for c in chunks)
        return httpx2.Response(
            200, content=body, headers={"Content-Type": "text/event-stream"}
        )

    return handler


async def main():
    with tempfile.TemporaryDirectory() as ws:
        seq1 = [
            make_chunk(
                tool_calls=[
                    {
                        "index": 0,
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "Write",
                            "arguments": '{"file_path":"out.txt","content":"hi"}',
                        },
                    }
                ]
            ),
            make_chunk(finish="tool_calls"),
        ]
        seq2 = [
            make_chunk(content="done"),
            make_chunk(finish="stop"),
        ]
        transport = httpx2.MockTransport(build_handler([seq1, seq2]))
        http_client = httpx2.AsyncClient(transport=transport)
        real_sdk = AsyncOpenAI(
            base_url="http://test", api_key="k", http_client=http_client
        )
        client = LLMClient(model="m", base_url="http://test", api_key="k", client=None)
        client._client = real_sdk
        agent = Agent(
            model="m",
            workspace=ws,
            permissions=[PermissionRule(tool="Write", behavior="allow")],
            llm_client=client,
        )
        result = await agent.run("write a file")
        check("e2e_status", result.status == "completed")
        check("e2e_text", result.text == "done")
        check("e2e_tool_called", len(result.tool_calls) == 1)
        check("e2e_file_written", __import__("os").path.exists(f"{ws}/out.txt"))

    print(f"\n{PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
