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
```

Configure each Bot's administrator, white, and black lists in the **平台账号** editor. Newly discovered conversations stay **待确认** until an administrator approves them or adds them to the white list. The default state path is `<project>/.agent/bridge`; keep it private because it contains conversation mappings, activity, and usage records. The management console is mounted at `/chat-agent/` on the existing NoneBot FastAPI server. The console token is generated and saved under the state directory if none is configured.

Configure the model connection under **接口能力**, then select that Provider and model on the Bot account. Reasoning effort is configured per account or group. Memories are shared by chats using the same `AGENT_WORKSPACE`; the `MEMORY.md` index and individual Markdown entries live under `<AGENT_WORKSPACE>/.agent/memory/`. The console's **记忆管理** page can create, edit, and delete entries and review group slang. Agents can read memories, while only Bot administrators can write them through chat.

## Behavior

- `chat` exposes conversation tools and read-only `WebSearch`, then sends the final reply. Configure `BRAVE_API_KEY` in the process environment to enable searches.
- `agent` accepts only administrator private messages and adds this repository's coding tools. Normal Agent permission rules and the approval callback still apply.
- Both modes include the configured persona or active role card in the system prompt. Agent mode also keeps that persona while using coding tools.
- The console's session table lets administrators choose enabled tools per conversation. New sessions enable all tools available in the current mode; changing modes clears session overrides and restores each session's defaults.
- `/status`, `/reset`, `/role [name|off]`, `/silent`, `/active`, `/mode <mode>`, and `/approve <yes|no>` are available to permitted chat users; state-changing commands require a Bot administrator.
- Chat targets are allowlisted by group or private peer. Replies are checked for credential-like values and local paths before sending, then split at configured message length.
- Incoming images are passed to vision-capable OpenAI-compatible models through Alconna's image fetch helper and size-limited inline data. Unsupported media remains an explicit text notice.
- `chat_save_meme` runs one vision pass that performs the safety review and recognises the image, storing a short name, 5-8 search keywords and a one-line summary in `memes.json` alongside the image. `chat_list_memes` accepts a `keywords` filter and returns that compact catalog so the model can pick a meme; `chat_send_meme` accepts the returned `file` or the short name. Legacy image files are backfilled into the index automatically.
- Media is sent as inline bytes (`base64://` on OneBot v11), not as a local `file:///` path, so it works when the OneBot implementation runs on another host or in a container.
- Speech uses a confined local audio library and offline `pyttsx3`; install `pyttsx3` plus a system speech engine to use synthesis. Adapters that cannot send audio return an error.
- Group slang extraction is rate-limited, researches candidates with the Agent's `WebSearch` / `WebFetch` tools, and leaves every result for administrator review before prompt injection.
- Memory-draft output is parsed defensively: code fences, trailing prose, concatenated JSON values, top-level arrays and envelope keys are all accepted, and list/dict field values are normalised to text. A batch that still fails keeps its buffered exchanges and is retried with exponential backoff (60 seconds up to 15 minutes), so one bad model reply cannot trigger a retry on every incoming message.
- The console provides persona and role-card management, global memory and slang management, initial prompts, approvals, and per-group or per-private-chat Agent transcripts with a clear button. It also shows activity, token and estimated-cost records and audio-library management. Set input/output cost rates per million tokens to enable cost estimates.

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
- **Group**: `adapter/platform + bot_id + group_id` identifies one group attached to one Bot. Group settings can override provider, model, prompt, reply frequency, reasoning effort, cost limit, and enabled tools.
- **Interfaces**: providers, skills, MCP servers, rules, and the runtime tool catalog are managed from the console. Provider records expose model discovery and preserve recognized context-window metadata for transcript compression.

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
