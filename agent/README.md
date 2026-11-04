# agent

一个可编程的、类 Claude Code 的 Python coding agent。它复刻了 `claude-code` 的基本功能：
**工作区选定、多轮对话 + 工具调用循环、可编程的安全/权限选项**，LLM 只对接
**OpenAI-compatible** `/chat/completions` 接口（基于官方 `openai` SDK）。

该包不依赖 NoneBot，可被任何 asyncio 应用 `import` 后直接调用。

## 安装

项目已用 `uv add openai` 添加依赖（`openai>=3.42.0`，其传输层为 `httpx2`）。
在项目根目录执行：

```bash
uv sync
```

## 快速开始

```python
import asyncio
from agent import Agent


async def main():
    # base_url / api_key / model 缺省读 OPENAI_BASE_URL / OPENAI_API_KEY / OPENAI_MODEL
    agent = Agent(
        model="your-model",
        workspace="D:/Projects/matrixbot/plugin-chatbot/plugin-chatbot",
        reasoning_effort="high",  # provider-dependent; omit to use provider default
        permission_mode="acceptEdits",  # default / acceptEdits / bypassPermissions / dontAsk / plan
    )
    result = await agent.run("读一下 README.md 并总结")
    print(result.text)
    await agent.close()


asyncio.run(main())
```

## 对外 API（`from agent import ...`）

| 符号 | 说明 |
| --- | --- |
| `Agent` | 主入口，可配置工作区、权限、工具、事件回调 |
| `Tool` | 工具定义（名称/描述/input_schema/handler/category） |
| `ToolCall` | 模型发起的一次工具调用 |
| `Message` | OpenAI 格式对话消息 |
| `AgentResult` | `run()` 的返回：text / messages / tool_calls / usage / status / error |
| `PermissionMode` | `default / acceptEdits / bypassPermissions / dontAsk / plan` |
| `PermissionRule` | 权限规则（tool + behavior: allow/deny/ask + pattern） |
| `LLMClient` / `LLMResponse` / `Usage` | LLM 客户端与响应/用量类型 |
| `LLMBackend` | LLM 后端协议，便于注入 mock 或自定义实现 |
| `builtin_tools()` | 默认内置工具集 |
| `SessionStore` / `SessionRecord` | 会话存储：多 chat + workspace 级 JSONL 持久化 |

### Agent 构造参数

```python
Agent(
    model=None,
    base_url=None,
    api_key=None,
    system_prompt=None,
    workspace=None,  # 主工作区目录（默认当前目录）
    permission_mode="default",  # default / acceptEdits / bypassPermissions / dontAsk / plan
    permissions=None,  # 初始 PermissionRule 列表（None 用 default_rules）
    additional_dirs=None,  # 附加工作区目录
    max_turns=25,
    temperature=0.7,
    tools=None,  # 自定义工具列表（None 用 builtin_tools）
    on_event=None,  # 事件回调 (event_name, payload)
    ask_callback=None,  # 权限确认回调，覆盖默认 ask()
    search_callback=None,  # WebSearch 提供者回调
    timeout=120.0,
    llm_client=None,  # 注入自定义 LLM 后端
    store=None,  # 自定义 SessionStore（默认用 store_root 或 workspace/.agent/sessions）
    store_root=None,  # 会话存储目录（默认 <workspace>/.agent/sessions）
    autosave=True,  # run() 结束后自动落盘
    max_context=262144,  # 上下文 token 预算
    compact_rate=0.8,  # 达到预算比例时压缩
    reasoning_effort=None,  # 或 low / medium / high；也可设 OPENAI_REASONING_EFFORT
    project_memory_enabled=True,
    project_memory_tools_enabled=True,
)
```

启用项目记忆后，同一 workspace 下的所有 Agent 会话共享 `<workspace>/.agent/memory/`。`MEMORY.md` 是自动维护且有大小上限的索引，每条主题记忆单独保存为 Markdown。索引会随每次模型请求注入；`ProjectMemoryRead` 用于按需读取，`ProjectMemoryWrite` 用于创建或更新。读取默认允许，写入遵循 Agent 权限模式。记忆提示要求只保存不能从当前工作区直接推导的长期信息，并将记忆内容视为不可信参考资料。可用 `project_memory_enabled=False` 关闭，或用 `project_memory_tools_enabled=False` 保留索引注入但不开放记忆工具。

每次请求的系统提示还会按当前实际开放的工具列出名称、用途和参数 schema；结构化工具定义也会继续通过 API 的 `tools` 字段发送。

运行前会估算整个请求的 token 数：系统提示词（含 persona、记忆索引与内联工具 schema）、`tools` 字段以及会话转录都计入预算，并用上一次模型响应返回的精确 `prompt_tokens` 校准估算偏差；达到 `max_context * compact_rate` 后，Agent 把较早历史（最多最近 50 条消息）转成扁平文本交给同一 LLM 总结、保留最近完整对话轮次，并原子替换该会话的 JSONL。总结请求只发送一条 `user` 消息，不会携带 `tool` 角色或 `tool_calls`，避免严格 provider 的协议校验失败。若总结后连同系统提示词仍超预算，则不再调用模型，直接硬裁剪（逐条截断超长工具输出、按回合丢弃最旧消息）。模型返回「上下文超限」时，Agent 会解析报错中的真实上限并强制压缩后自动重试一次；遇到中止/崩溃留下的悬空 `tool_calls`，下一轮开始前会自动补齐占位工具结果，保证转录始终合法。实测 token 数与转录估算值保存在会话元数据中，按模型、系统提示词和工具集指纹隔离。图像 token 成本仍由模型服务商决定，无法仅从 JSONL 通用地精确还原。

### 核心方法

- `await agent.run(prompt) -> AgentResult`：发起一轮对话（自动多轮工具调用直至收敛或达 max_turns）
- `await agent.ask(question) -> bool`：权限确认，可被 `ask_callback` 覆盖；默认拒绝
- `agent.abort()`：中止当前对话
- `agent.set_permission_mode(mode)` / `agent.update_permissions(rules)`：运行中修改安全选项
- `agent.history() -> list[Message]`：对话历史（当前 chat）
- `agent.new_chat(alias=None, title=None) -> str`：新建 chat，返回 chat_id 并设为当前
- `agent.load_chat(chat_id) -> SessionRecord`：从磁盘装载历史并设为当前
- `agent.use_chat(chat_id) -> SessionRecord`：切换到已存在 chat（惰性加载）
- `agent.current_chat() -> str | None`：当前 chat_id
- `agent.list_chats() -> list[SessionRecord]`：列出该 workspace 下所有 chat
- `agent.save()` / `agent.save_all()`：显式落盘
- `agent.delete_chat(chat_id) -> bool`：删除 chat
- `await agent.close()`：关闭底层 HTTP 连接

### 事件回调 `on_event(name, payload)`

- `text_delta`：增量文本
- `tool_call_start` / `tool_result`：工具调用与结果
- `permission_check`：权限判定结果（behavior）
- `permission_ask`：请求用户确认

## 安全 / 权限模型

镜像 `claude-code` 的判定优先级：

1. 显式 `deny` 规则优先拒绝
2. 危险路径保护（`.git/`、`.env`、`.vscode/`、`.ssh/` 等）即使 `bypassPermissions` 也强制 ask
3. 显式 `allow` / `ask` 规则
4. 按模式：`bypassPermissions` 放行；`dontAsk` 拒绝；`acceptEdits` 允许工作区内写；
   `default`/`plan` 下读工作区内放行，写/命令需确认

工作区判定基于 `realpath` 归一化 + 前缀包含（含 symlink 解析），`additional_dirs` 可扩展。

## 内置工具

`Bash`、`Read`、`Write`、`Edit`、`Glob`、`Grep`、`WebFetch`、`WebSearch`。
`WebSearch` 默认未配置，需设置 `BRAVE_API_KEY` 或传入 `search_callback`。

## 自定义工具

```python
from agent import Tool


async def my_handler(args, ctx):
    return f"hello {args['name']}"


my_tool = Tool(
    name="Hello",
    description="Say hello",
    input_schema={
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    },
    handler=my_handler,
    category="exec",
)
```

## 多 chat + 持久化

参考 `claude-code` 的会话转录模型：每个 chat 一个 JSONL 文件，逐条追加。存储目录设在
**workspace 级别**（默认 `<workspace>/.agent/sessions/`），可用 `store_root` 或 `store`
覆盖。`.agent/` 已加入 `.gitignore`，会话数据不入库。

```python
from agent import Agent


async def main():
    agent = Agent(
        model="your-model",
        workspace="D:/Projects/matrixbot/plugin-chatbot/plugin-chatbot",
        permission_mode="acceptEdits",
    )

    # 新建 chat（可选绑定别名），返回 chat_id
    chat_id = agent.new_chat(alias="demo")
    result = await agent.run("先看一下仓库结构")
    print(result.text)

    # 同实例内切换到另一个 chat，历史互不污染
    other_id = agent.new_chat(alias="another")
    await agent.run("另一个会话的问题")

    # 切回第一个 chat，历史自动注入续接
    agent.use_chat(chat_id)  # 或 agent.use_chat("demo") 用别名
    result = await agent.run("接着上一个问题继续")
    print(result.text)

    # 重启进程后加载已有 chat 续接
    agent2 = Agent(
        model="your-model",
        workspace="D:/Projects/matrixbot/plugin-chatbot/plugin-chatbot",
    )
    agent2.load_chat(chat_id)
    await agent2.run("恢复会话后的追问")

    # 列出所有 chat / 显式落盘
    for rec in agent2.list_chats():
        print(rec.chat_id, rec.alias, rec.title, rec.message_count)
    agent2.save_all()

    await agent.close()
    await agent2.close()


asyncio.run(main())
```

`run()` 结束自动落盘（`autosave=True`）；`autosave=False` 时需显式 `save()` / `save_all()`。
`run(prompt, chat_id=...)` 可指定目标 chat（缺省用当前 chat，无则自动 new）。

## 测试

测试为自包含脚本（无需 pytest）：

```bash
.venv/Scripts/python.exe tests/test_permissions.py
.venv/Scripts/python.exe tests/test_tools.py
.venv/Scripts/python.exe tests/test_core.py
.venv/Scripts/python.exe tests/test_llm.py
.venv/Scripts/python.exe tests/test_e2e.py
.venv/Scripts/python.exe tests/test_store.py
.venv/Scripts/python.exe tests/test_chat_store.py
```

静态检查：

```bash
.venv/Scripts/python.exe -m ruff check agent tests
.venv/Scripts/python.exe -m ruff format --check agent tests
.venv/Scripts/python.exe -m pyright agent tests
```
