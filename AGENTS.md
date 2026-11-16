# AGENTS.md

给在本仓库工作的 AI 编码助手看的约定。功能、配置与 API 的完整说明在
[README](README.md) 与 [docs/](docs/) 里，本文只讲动手改代码前要知道的事，
细节以链接到的文档为准，不要在这里复制它们。

## 这是什么

把通用 NoneBot 消息事件接进自研的 Python `Agent`：多轮对话、工具调用、人格、
记忆与权限都由 Agent 负责，收发消息与目标解析交给
[nonebot-plugin-alconna](https://github.com/NoneBot/plugin-alconna)
（`UniMessage` / `Target`），因此桥接层不直接调 OneBot API，各种适配器都能接。

## 代码地图

| 路径 | 是什么 |
| --- | --- |
| `agent/` | 可编程的、类 Claude Code 的 Python coding agent。**不依赖 NoneBot**，可被任何 asyncio 应用 import。核心：`core.py`（Agent 主循环）、`permissions.py`、`tool.py`、`llm.py`、`store.py`、`memory.py`、`context.py`。API 见 [docs/agent.md](docs/agent.md) |
| `plugin_chatbot/bridge/` | 桥接层：`service.py`（消息收发/投递/会话映射/后台 API）、`custom_tools*.py`、`memes.py`、`slang.py`、`voice.py`、`mentions.py`、`roles.py`。行为见 [docs/features.md](docs/features.md) |
| `plugin_chatbot/plugins/chat_bridge.py` | NoneBot 插件入口，加载桥接 |
| `plugin_chatbot/plugins/webui/` | 后台前端**构建产物**（由 `webui/` 生成），不要手改 |
| `webui/` | 管理后台前端源码，Vite + React。结构与视觉规范见 [docs/console.md](docs/console.md) |
| `tests/` | 自包含测试脚本，见下文「验证」 |
| `.agent/` | 运行时数据（会话、记忆、bridge 状态），已 gitignore，**永不提交** |

改 `agent/` 是改一个通用库；改 `plugin_chatbot/bridge/` 是改 NoneBot 桥接；
两者边界要守住，`agent/` 里不要引入 NoneBot 依赖。

## 命令

依赖用 `uv` 管理（`uv sync`）；也可 `pip install -e .`。Python `>=3.10, <4.0`。

```powershell
# 测试（unittest discover，无需 pytest）
.venv\Scripts\python.exe -m unittest discover -s tests -v

# Lint + 类型检查（改完必跑）
.venv\Scripts\ruff.exe check --no-cache agent plugin_chatbot tests
.venv\Scripts\pyright.exe agent plugin_chatbot tests
```

前端构建 / 联调：

```powershell
cd webui
npm install
npm run build   # 产物复制到 plugin_chatbot/plugins/webui/
npm run dev     # http://localhost:5178/，/chat-agent 代理到 NoneBot（CHATBOT_BACKEND 可覆盖）
```

## 代码风格

- 用 ruff + pyright 把关，行宽 **88**，`line-ending = lf`，target py39（运行时 3.10+）。
- 启用的规则很严（annotations、async、bugbear、pyupgrade、tryceratops 等），
  见 `pyproject.toml` 的 `[tool.ruff.lint]`。补全类型注解，别用 `# type: ignore` 绕过。
- `pyproject.toml` 里对 `tests/*` 放宽了很多规则，测试脚本可以宽松些。
- 几个刻意的忽略项别「修」：`E402`（NoneBot `require()` 要求）、`B008`
  （NoneBot `Depends()` 无 Annotated）、`ANN202`、`ANN401`、`COM812`、`PLC0415`。

## 验证约定

- 测试是**自包含脚本**，大多不依赖 pytest，直接 `python tests/test_xxx.py` 跑；
  也可 `unittest discover -s tests`。写新测试沿用同目录现有脚本的风格。
- 已有针对 `agent`（`test_core/test_tools/test_permissions/test_llm/test_e2e/
  test_store/test_chat_store/test_context`）与 `bridge`（`test_bridge*`、
  `test_memes`、`test_slang`、`test_persona_drift`、`test_reply_probability` 等）
  的覆盖，改对应模块要补/跑相关测试。
- 改了 README 里可验证的命令或示例，留意 `tests/test_readme_smoke.py`。

## 安全红线

- `.agent/`（会话转录、记忆、`bridge-state.json`、voice、custom_tools 源码）
  含隐私与运行时数据，**绝不提交**，也不要在示例/日志里打印其内容。
- `BRIDGE_STATE_DIR`、`BRIDGE_CONSOLE_TOKEN`、API key 一律视为机密。
- 危险路径（`.git/`、`.env`、`.ssh/` 等）即使 `bypassPermissions` 也强制确认，
  改 `agent/permissions.py` 时别破坏这套优先级
  （deny > 危险路径 > allow/ask > 模式默认），见 [docs/agent.md](docs/agent.md)。
- 自定义 Tool 以 Bot 进程的系统权限在子进程跑，等于宿主 shell；动
  `custom_tool_runner.py` 要格外谨慎（隔离 `-I` 只隔离导入路径，不隔离文件系统）。
- 任何.venv 文件都有可能包含机密数据，**绝不提交**，也不要在示例/日志里打印其内容。
