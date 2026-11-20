# 配置说明

配置写在 NoneBot 配置文件 `.env` 或 `.env.*` 中，由插件配置读取：下表的环境变量名即插件配置字段名的大写形式，未写的项使用默认值。

## 运行与路径

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `AGENT_WORKSPACE` | 项目根目录 | Bot 的工作区。Agent 的工具以此为根，同工作区的会话与记忆互相共享。 |
| `BRIDGE_STATE_DIR` | `<项目根>/.agent/bridge` | 桥接状态目录，`bridge-state.json` 与各类运行数据都在这里。内含会话映射、活跃度与用量记录，请勿公开。 |
| `BRIDGE_MODE` | `chat` | 运行模式，`chat` 或 `agent`；非法值按 `chat` 处理。 |
| `BRIDGE_CONSOLE_TOKEN` | 自动生成 | 管理后台访问令牌。不配置时会生成一份并保存到状态目录下的 `console-token`。 |

## 消息与投递

| 变量 | 默认值 | 取值 | 说明 |
| --- | --- | --- | --- |
| `BRIDGE_MAX_MESSAGE_CHARS` | `500` | 100–4000 | 单条回复切分长度。 |
| `BRIDGE_MAX_MESSAGES_PER_MINUTE` | `6` | 1–60 | 每个会话每分钟最多主动发出的消息条数。 |
| `BRIDGE_GROUP_BATCH_SECONDS` | `1.0` | 0–10 | 群消息合并窗口，同一窗口内的消息一并投递。 |
| `BRIDGE_MAX_MEDIA_BYTES` | `8388608`（8 MiB） | 1 KiB–32 MiB | 单条媒体的字节上限，同时用于内联图片与表情包展示。 |

## 上下文与成本

| 变量 | 默认值 | 取值 | 说明 |
| --- | --- | --- | --- |
| `MAX_CONTEXT` | `262144` | 4096–2000000 | 上下文 token 预算，达到预算比例后触发压缩。 |
| `COMPACT_RATE` | `0.8` | 0.1–0.99 | 压缩触发阈值（占预算比例）。 |
| `BRIDGE_INPUT_COST_PER_MILLION` | `0` | 任意 | 输入侧每百万 token 的计费价，用于估算成本。 |
| `BRIDGE_OUTPUT_COST_PER_MILLION` | `0` | 任意 | 输出侧每百万 token 的计费价，用于估算成本。 |

成本估算只是把 token 数乘以单价，真实账单以服务商为准；两项都保持 `0` 即关闭估算。

## 语音

| 变量 | 默认值 | 取值 | 说明 |
| --- | --- | --- | --- |
| `BRIDGE_VOICE_DIR` | `<状态目录>/voices` | 路径 | 受限的本地音频库目录。 |
| `BRIDGE_VOICE_MAX_BYTES` | `20971520`（20 MiB） | ≥ 1 KiB | 单个音频文件大小上限。 |
| `BRIDGE_VOICE_SENDS_PER_HOUR` | `20` | 1–500 | 每小时语音发送上限。 |

## 搜索与黑话

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `BRAVE_API_KEY` | 空 | **进程环境变量**（不是插件配置项），配置后 `chat` 模式的内置 `WebSearch` 可用。 |
| `BRIDGE_MCP_SERVER_URL` | 空 | 可选的 streamable HTTP MCP 服务器地址，用于 `open_websearch` 通道。 |
| `BRIDGE_SLANG_ENABLED` | `true` | 是否启用群黑话抽取。 |
| `BRIDGE_SLANG_MIN_MESSAGES` | `10`（3–100） | 触发一次抽取所需的最少消息数。 |
| `BRIDGE_SLANG_COOLDOWN_SECONDS` | `300` | 两次抽取之间的冷却时间。 |

## 表情包

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `BRIDGE_MEME_UPLOAD_ENABLED` | `true` | 是否允许新增表情包（同时管 WebUI 上传与 `chat_save_meme`）。 |

## 示例

```dotenv
AGENT_WORKSPACE=D:/path/to/workspace
BRIDGE_STATE_DIR=D:/path/to/private-bridge-state
BRIDGE_MODE=chat
BRIDGE_MAX_MESSAGE_CHARS=500
BRIDGE_MAX_MEDIA_BYTES=8388608
BRIDGE_CONSOLE_TOKEN=replace-with-a-long-random-token
BRIDGE_VOICE_DIR=D:/path/to/voice-library
BRIDGE_VOICE_MAX_BYTES=20971520
BRIDGE_VOICE_SENDS_PER_HOUR=20
BRIDGE_SLANG_ENABLED=true
BRIDGE_SLANG_MIN_MESSAGES=10
BRIDGE_SLANG_COOLDOWN_SECONDS=300
BRIDGE_INPUT_COST_PER_MILLION=0
BRIDGE_OUTPUT_COST_PER_MILLION=0
BRAVE_API_KEY=
BRIDGE_MCP_SERVER_URL=
BRIDGE_MEME_UPLOAD_ENABLED=true
```

## 三层配置

管理后台把配置分成三层，均保存在 `BRIDGE_STATE_DIR` 下的 `bridge-state.json` 中：

- **账号**：`adapter/platform + bot_id` 标识一个已连接的 Bot。每个 Bot 选择已配置的 Provider 与模型，并各自持有推理强度、上下文回退、人格模板、补充提示词、启用工具与访问名单。
- **群组**：`adapter/platform + bot_id + group_id` 标识挂在某个 Bot 下的一个群。群设置可以覆盖 Provider、模型、提示词、回复概率、推理强度、成本上限与启用工具。
- **接口**：Provider、技能、MCP 服务器、规则与运行时工具目录都在后台管理。Provider 记录支持模型发现，并保留已识别的上下文窗口元数据用于转录压缩。**MCP** 标签页额外承载一张内置的 `open_websearch` 连接卡（启用开关、服务地址、连接 / 重新发现、连接状态与已发现的工具），通过 `GET/PUT /api/mcp` 写入持久化的顶层 `mcp_server_url`；`interfaces.mcps` 列表仍只是目录。当前只支持一个 streamable HTTP MCP 服务器，它暴露的工具名固定带 `mcp__open_websearch__` 前缀，其中的 `search` 工具会隐藏内置 `WebSearch`。

人格模板在 **人格提示** 工作台里管理：账号可以选一个模板再加自己的补充，群提示词一旦存在就完全覆盖账号人格。**Tools** 标签页列出当前模式下可用的工具，账号与群可以选择继承或收窄默认值。

## 已停用的变量

以下设置已不再被桥接读取，功能相应移到了后台：`AGENT_MODEL`、`AGENT_BASE_URL`、`AGENT_API_KEY`、`AGENT_REASONING_EFFORT`、`BRIDGE_OWNER_IDS`、`BRIDGE_ALLOWED_GROUPS`、`BRIDGE_ALLOWED_PRIVATE`。

模型连接在后台 **接口能力** 里配置，然后在平台账号上选择该 Provider 与模型；推理强度按账号或群配置。管理员、白名单与黑名单在 **平台账号** 编辑器里配置，新发现的会话保持 **待确认**，直到管理员批准或加进白名单。
