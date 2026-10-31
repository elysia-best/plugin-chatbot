"""README 用法冒烟测试：仅用公开 API，注入脚本化 LLM 避免网络。"""

import asyncio
import sys
import tempfile

sys.path.insert(0, ".")

from agent import Agent
from agent.llm import LLMResponse
from agent.messages import ToolCall
from agent.permissions import PermissionRule


class StatefulLLM:
    """第一轮返回 Write 工具调用，第二轮返回最终文本。"""

    def __init__(self):
        self.calls = 0

    async def complete(self, messages, tools=None, system_prompt=None):
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="Write",
                        arguments={"file_path": "demo.txt", "content": "hello"},
                    )
                ]
            )
        return LLMResponse(content="总结完成")


async def main():
    with tempfile.TemporaryDirectory() as ws:
        agent = Agent(
            model="m",
            workspace=ws,
            permissions=[PermissionRule(tool="Write", behavior="allow")],
        )
        agent._llm = StatefulLLM()
        result = await agent.run("写个文件并总结")
        assert result.status == "completed", result
        assert len(result.tool_calls) == 1, result.tool_calls
        assert result.tool_calls[0].name == "Write", result.tool_calls
        assert result.text == "总结完成", result.text
        print("README usage smoke test: PASSED")


if __name__ == "__main__":
    asyncio.run(main())
