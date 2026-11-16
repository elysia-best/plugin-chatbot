<div align="center">

# Plugin-Chatbot

_✨ NoneBot AI 聊天机器人 ✨_

</div>

## 简介

把通用的 NoneBot 消息事件接进本仓库的 Python `Agent`：多轮对话、工具调用、人格、记忆与权限都由 Agent 负责，收发消息与目标解析则交给 [nonebot-plugin-alconna](https://github.com/NoneBot/plugin-alconna)（`UniMessage` / `Target`），因此桥接层不直接调用 OneBot API，各种适配器都能接。

管理后台可以把同一个 Bot 挂到多个平台账号上，按账号、按群分别配置模型、人格、工具与回复策略。功能细节见 [docs/功能说明](docs/features.md)。

## 安装

在项目根目录安装依赖：

```bash
uv sync
```

已有 NoneBot 项目时也可以直接装上本项目：

```bash
pip install -e .
```

## 配置

修改 NoneBot 配置文件 `.env` 或 `.env.*`。

### AGENT_WORKSPACE

Bot 的工作区目录。Agent 的工具调用以此为根，同一工作区下的会话和记忆互相共享。

```dotenv
AGENT_WORKSPACE=D:/path/to/workspace
```

### BRIDGE_STATE_DIR

桥接状态目录，`bridge-state.json` 与各类运行数据都写在这里，默认 `<项目根>/.agent/bridge`。目录里有会话映射、活跃度和用量记录，请勿公开。

```dotenv
BRIDGE_STATE_DIR=D:/path/to/private-bridge-state
```

### BRIDGE_MODE

运行模式，默认为 `chat`。`chat` 对外提供对话工具与只读搜索；`agent` 只接受管理员私聊，并额外开放编码工具。

```dotenv
BRIDGE_MODE=chat
```

### BRIDGE_CONSOLE_TOKEN

管理后台的访问令牌。不配置时会自动生成一份并保存到状态目录下的 `console-token`。

```dotenv
BRIDGE_CONSOLE_TOKEN=replace-with-a-long-random-token
```

### 其他配置项

消息切分长度、媒体大小、语音、黑话、成本估算、Brave 搜索、MCP 服务器与表情包上传等开关，见 [配置说明](docs/configuration.md)。

### 示例

```dotenv
AGENT_WORKSPACE=D:/path/to/workspace
BRIDGE_STATE_DIR=D:/path/to/private-bridge-state
BRIDGE_MODE=chat
BRIDGE_CONSOLE_TOKEN=replace-with-a-long-random-token
BRIDGE_MAX_MESSAGE_CHARS=500
BRIDGE_MAX_MEDIA_BYTES=8388608
```

## 启动

把 `plugin_chatbot.plugins.chat_bridge` 加进 NoneBot 的插件加载列表（或在 `pyproject.toml` 中配置项目插件目录），再按平时的方式启动 NoneBot。

## 管理后台

后台挂载在 NoneBot 既有的 FastAPI 服务器上，默认地址为 <http://127.0.0.1:8080/chat-agent/>。

首次使用时依次完成：在 **接口能力** 配置模型连接 → 在 **平台账号** 选择 Provider 与模型、配置管理员和白黑名单 → 在 **群聊策略** 设置回复概率与群提示词。新发现的会话处于 **待确认** 状态，需要管理员批准或加进白名单。

后台前端是独立的 `webui/` 项目，运行前需要先构建一次：

```powershell
cd webui
npm install
npm run build
```

页面一览、联调方式与视觉规范见 [管理后台](docs/console.md)。

## 指令

`/status`、`/reset`、`/role [name|off]`、`/reply [0..1]`、`/mode <mode>`、`/approve <yes|no>` 对所有被允许的聊天用户开放，其中会改变状态的指令需要 Bot 管理员身份。群聊的回复概率也可在后台 **群聊策略** 页面设置。

## 文档

| 文档 | 内容 |
| --- | --- |
| [功能说明](docs/features.md) | 运行模式、人格与身份一致性、群聊策略、记忆、黑话、表情包、语音、自定义 Tool。 |
| [配置说明](docs/configuration.md) | 环境变量全表、三层配置、已停用的变量。 |
| [管理后台](docs/console.md) | 后台页面、前端构建与开发、结构与视觉规范。 |
| [agent 包](docs/agent.md) | Agent 的 API、权限模型与会话持久化。 |

## 开发检查

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\ruff.exe check --no-cache agent plugin_chatbot tests
.venv\Scripts\pyright.exe agent plugin_chatbot tests
```
