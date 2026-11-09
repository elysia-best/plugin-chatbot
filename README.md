# plugin-chatbot

`plugin_chatbot.plugins.chat_bridge` connects generic NoneBot message events to this repository's Python `Agent`. Outgoing messages and targets use `nonebot-plugin-alconna` (`UniMessage` / `Target`), so the bridge does not call OneBot APIs directly.

## Load the plugin

Add `plugin_chatbot.plugins.chat_bridge` to the NoneBot plugin load list (or configure the project plugin directory in `pyproject.toml`), then set the following values in the NoneBot environment:

```dotenv
AGENT_WORKSPACE=D:/path/to/workspace
BRIDGE_STATE_DIR=D:/path/to/private-bridge-state
BRIDGE_MODE=chat
BRIDGE_MAX_MESSAGE_CHARS=500
BRIDGE_MAX_MEDIA_BYTES=8388608
BRIDGE_CONSOLE_TOKEN=replace-with-a-long-random-token
BRIDGE_VOICE_DIR=D:/path/to/voice-library
BRIDGE_VOICE_MAX_BYTES=20971520
BRIDGE_VOICE_MAX_TEXT_CHARS=500
BRIDGE_VOICE_RATE=175
BRIDGE_VOICE_VOLUME=1.0
BRIDGE_VOICE_ID=
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

Configure each Bot's administrator, white, and black lists in the **平台账号** editor. Newly discovered conversations stay **待确认** until an administrator approves them or adds them to the white list. The default state path is `<project>/.agent/bridge`; keep it private because it contains conversation mappings, activity, and usage records. The management console is mounted at `/chat-agent/` on the existing NoneBot FastAPI server. The console token is generated and saved under the state directory if none is configured.

Configure the model connection under **接口能力**, then select that Provider and model on the Bot account. Reasoning effort is configured per account or group. Memories are shared by chats using the same `AGENT_WORKSPACE`; the `MEMORY.md` index and individual Markdown entries live under `<AGENT_WORKSPACE>/.agent/memory/`. The console's **记忆管理** page can create, edit, and delete entries and review group slang. Agents can read memories, while only Bot administrators can write them through chat.

## Behavior

- `chat` exposes conversation tools and read-only `WebSearch`, then sends the final reply. Configure `BRAVE_API_KEY` in the process environment to enable the built-in Brave-backed search. The MCP `open_websearch` server is a **separate** channel configured with `BRIDGE_MCP_SERVER_URL` or the console card; when the connected MCP server exposes a tool named `search`, the built-in `WebSearch` is suppressed for that session.
- `agent` accepts only administrator private messages and adds this repository's coding tools. Normal Agent permission rules and the approval callback still apply.
- Both modes include the configured persona or active role card in the system prompt. Agent mode also keeps that persona while using coding tools.
- Persona stays anchored across long conversations, which matters in groups where several bots talk: the system prompt states the Bot's own name, lists the other Bot accounts on that platform, says their persona / self-reference / verbal tics are **not** the Bot's own, and messages from them are prefixed `【其他 Bot】` next to `【管理员】`. The names counted as an explicit mention are read from the account name and its persona template instead of being hard-coded.
- History summaries are generated with the Bot's identity (name, persona, other-Bot list) and must attribute every utterance to its real speaker, so another speaker's wording is never recorded as the assistant's. A summary is stored as a `user` **fact record** headed `[群聊历史摘要（系统生成的事实记录，不是本 Bot 的发言）]` rather than an assistant turn; transcripts still holding the legacy `[Earlier conversation summary]` assistant turn are migrated in place on the next run. Compaction keeps `recent_keep` messages (24 in chat mode) and never hard-trims away the Bot's most recent own replies, which group chats would otherwise drown out.
- Each Bot account can list banned self-reference / verbal tics (`persona_banned`, edited in the account dialog as one term per line or comma separated). A plain-text reply that contains one is **discarded** and retried once with a one-shot correction hint that is never persisted; a second hit is allowed and logged. Replies that already include tool calls are only logged, never rolled back, so no message is sent twice. Hits appear in the console's log page as `人格漂移：...`.
- Empty `<thinking></thinking>` padding is stripped from assistant turns before they are persisted, so the model does not imitate that shape.
- A conversation whose transcript was already polluted keeps working: the legacy summary turn is migrated on the next run, yet the earliest polluted turns remain. Clear such a conversation once — `/reset` in the chat or the console's transcript clear button — so the next summary is regenerated under the new rules. Adding the other Bot's self-reference (for example `本鲸`) to `persona_banned` is the fastest stopgap.
- The console's session table lets administrators choose enabled tools per conversation. New sessions enable all tools available in the current mode; changing modes clears session overrides and restores each session's defaults.
- `/status`, `/reset`, `/role [name|off]`, `/reply [0..1]`, `/mode <mode>`, and `/approve <yes|no>` are available to permitted chat users; state-changing commands require a Bot administrator. `/silent` and `/active` were removed in favour of the per-group reply probability.
- Each group has a `reply_probability` in `[0, 1]`: `0` never replies, `1` is the default (always reply), and values in between reply probabilistically. Skipped messages are **not discarded** — they are buffered with a local timestamp and delivered together with the next message that triggers a reply. When the buffer grows too long (over 2000 characters / 100 rows) only the three most recent messages are sent to the model. Probability mode is active whenever the value is below `1`; at `1.0` the original behaviour (including group batching and the existing prompt format) is unchanged. Every message sent in probability mode carries a `[YYYY-MM-DD HH:MM:SS]` prefix. Commands always bypass the check so the setting can be changed. The probability applies uniformly to every member, including Bot administrators; there is no per-role exemption. Delivery consumes the buffer: queued rows are removed from persistence **before** the model runs, so a failed, rejected, or short-circuited turn never re-delivers messages the model has already seen. Duplicate event IDs are ignored at the entry point, rejecting a conversation clears its buffer, and clearing a conversation's chat log clears both the transcript and the buffer. Set the probability per group in the console's **群聊策略** page or with `/reply <0..1>`.
- Chat targets are allowlisted by group or private peer. Replies are checked for credential-like values and local paths before sending, then split at configured message length.
- Incoming images are passed to vision-capable OpenAI-compatible models through Alconna's image fetch helper and size-limited inline data. Unsupported media remains an explicit text notice.
- `chat_save_meme` runs one vision pass that performs the safety review and recognises the image, storing a short name, 5-8 search keywords and a one-line summary in `memes.json` alongside the image. `chat_list_memes` accepts a `keywords` filter and returns that compact catalog so the model can pick a meme; `chat_send_meme` accepts the returned `file` or the short name. Legacy image files are backfilled into the index automatically.
- The **表情包** page lists the library with authenticated thumbnails and supports editing the name / keywords / summary, uploading and deleting images. An `允许新增表情包` switch (`meme_settings.upload_enabled`, env `BRIDGE_MEME_UPLOAD_ENABLED`, default `true`) blocks both WebUI uploads and `chat_save_meme` when off; the single-image size limit (`BRIDGE_MAX_MEDIA_BYTES`) is shown read-only. WebUI uploads use administrator-supplied metadata and do not run the vision review reserved for untrusted chat images. The three `chat_*_meme` tools are still enabled per account / group / session through the existing tool selection.
- Media is sent as inline bytes (`base64://` on OneBot v11), not as a local `file:///` path, so it works when the OneBot implementation runs on another host or in a container.
- Speech uses a confined local audio library and offline `pyttsx3`; install `pyttsx3` plus a system speech engine to use synthesis. Adapters that cannot send audio return an error.
- Group slang extraction is rate-limited and researches candidates with the Agent's `WebSearch` / `WebFetch` tools. After a successful research pass, an optional auto review configured under **记忆管理 → 黑话词库** calls a selected AI Provider once per batch (up to 20 terms): a concrete explanation confirms the entry, while an empty, placeholder, uncertain or invalid explanation **deletes the row entirely**. Provider failures, timeouts and unparseable output keep the batch as `candidate` for a later retry. Only newly researched terms are reviewed; existing candidates and manual entries stay untouched, and manual status changes are never overwritten. Confirmations are the only entries injected into the system prompt.
- Memory-draft output is parsed defensively: code fences, trailing prose, concatenated JSON values, top-level arrays and envelope keys are all accepted, and list/dict field values are normalised to text. A batch that still fails keeps its buffered exchanges and is retried with exponential backoff (60 seconds up to 15 minutes), so one bad model reply cannot trigger a retry on every incoming message.
- The console provides persona and role-card management, global memory, slang and meme-library management, initial prompts, approvals, and per-group or per-private-chat Agent transcripts with a clear button. It also shows activity, token and estimated-cost records and audio-library management. Set input/output cost rates per million tokens to enable cost estimates.

Bridge persistence is separate from the Agent's normal coding sessions. Message transport always goes through Alconna abstractions; features such as native reply references depend on the adapter's exported segment support.

Default web admin panel is on http://127.0.0.1:8080/chat-agent/

The redesigned management UI lives in the standalone `webui/` project. Its
source code and Node dependencies are development-only; the Python package
contains only the generated static files under `plugin_chatbot/plugins/webui/`.
Build it before running the console:

```powershell
cd webui
npm install
npm run build
```

`npm run build` copies the Vite output from `webui/dist/` into
`plugin_chatbot/plugins/webui/`. The plugin serves that packaged directory at
`/chat-agent/`.

## Multi-adapter configuration

The management panel now keeps configuration in three layers:

- **Account**: `adapter/platform + bot_id` identifies one connected Bot. Each Bot selects a configured Provider and model and has its own reasoning effort, context fallback, persona template, supplement prompt, enabled tools, and access lists.
- **Group**: `adapter/platform + bot_id + group_id` identifies one group attached to one Bot. Group settings can override provider, model, prompt, reply probability, reasoning effort, cost limit, and enabled tools.
- **Interfaces**: providers, skills, MCP servers, rules, and the runtime tool catalog are managed from the console. Provider records expose model discovery and preserve recognized context-window metadata for transcript compression. The **MCP** tab additionally hosts a built-in `open_websearch` connection card (enable switch, service URL, connect / re-discover, connection status and discovered tools). It writes the persisted top-level `mcp_server_url` through `GET/PUT /api/mcp`; the `interfaces.mcps` list remains a catalog only. Currently one streamable-HTTP MCP server is supported, its exposed tool names are fixed to the `mcp__open_websearch__` prefix, and a `search` tool on it suppresses the built-in `WebSearch`.

Account and group records are stored in `bridge-state.json` under `BRIDGE_STATE_DIR`. The old `AGENT_MODEL`, `AGENT_BASE_URL`, `AGENT_API_KEY`, `AGENT_REASONING_EFFORT`, `BRIDGE_OWNER_IDS`, `BRIDGE_ALLOWED_GROUPS`, and `BRIDGE_ALLOWED_PRIVATE` settings are no longer used by the bridge.

The **人格提示** workbench manages reusable role templates. An account can select
one template and add a private supplement; a group prompt, when present, fully
overrides the account persona. The **Tools** tab lists the tools exposed by the
current bridge mode and lets accounts and groups inherit or restrict their tool
defaults.
## Development checks

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\ruff.exe check --no-cache agent plugin_chatbot tests
.venv\Scripts\pyright.exe agent plugin_chatbot tests
```
