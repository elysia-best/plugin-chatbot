# plugin-chatbot

`plugin_chatbot.plugins.chat_bridge` connects generic NoneBot message events to this repository's Python `Agent`. Outgoing messages and targets use `nonebot-plugin-alconna` (`UniMessage` / `Target`), so the bridge does not call OneBot APIs directly.

## Load the plugin

Add `plugin_chatbot.plugins.chat_bridge` to the NoneBot plugin load list (or configure the project plugin directory in `pyproject.toml`), then set the following values in the NoneBot environment:

```dotenv
AGENT_MODEL=your-model
AGENT_BASE_URL=https://your-openai-compatible-endpoint/v1
AGENT_API_KEY=your-key
AGENT_REASONING_EFFORT=medium
AGENT_WORKSPACE=D:/path/to/workspace
BRIDGE_OWNER_IDS=123456,234567
BRIDGE_ALLOWED_GROUPS=group-a,group-b
BRIDGE_ALLOWED_PRIVATE=user-a,user-b
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

Without configured owner IDs or allowlists, only configured owners can use the bridge. The default state path is `<project>/.agent/bridge`; keep it private because it contains conversation mappings, activity, and usage records. The management console is mounted at `/chat-agent/` on the existing NoneBot FastAPI server. The console token is generated and saved under the state directory if none is configured.

`AGENT_REASONING_EFFORT` is optional and is forwarded as `reasoning_effort` to the configured OpenAI-compatible model. Use a value supported by that provider, commonly `low`, `medium`, or `high`. Project memories are shared by chats using the same `AGENT_WORKSPACE`; the `MEMORY.md` index and individual Markdown entries live under `<AGENT_WORKSPACE>/.agent/memory/`. The console's **项目记忆** page can create, edit, and delete entries. Agents can read memories, while only configured owners can write them through chat.

## Behavior

- `chat` exposes only the current-chat tools plus read-only `WebSearch` and sends a final agent reply. Configure `BRAVE_API_KEY` in the process environment to enable searches.
- `reserved` applies the same safe tool surface and suppresses a response consisting of `[SILENT]`.
- `reserved2` treats an incoming message as an agent wake-up and sends only messages explicitly emitted through `chat_send`.
- `closed-agent` accepts only owner private messages and adds this repository's coding tools. Their normal Agent permission rules and approval callback still apply.
- The console's session table lets administrators choose enabled tools per conversation. New sessions enable all tools available in the current mode; changing modes clears session overrides and restores each session's defaults.
- `/status`, `/reset`, `/role [name|off]`, `/silent`, `/active`, `/mode <mode>`, and `/approve <yes|no>` are available to permitted chat users; state-changing commands require an owner.
- Chat targets are allowlisted by group or private peer. Replies are checked for credential-like values and local paths before sending, then split at configured message length.
- Incoming images are passed to vision-capable OpenAI-compatible models through Alconna's image fetch helper and size-limited inline data. Unsupported media remains an explicit text notice.
- Speech uses a confined local audio library and offline `pyttsx3`; install `pyttsx3` plus a system speech engine to use synthesis. Adapters that cannot send audio return an error.
- Group slang extraction is rate-limited, researches candidates with the Agent's `WebSearch` / `WebFetch` tools, and leaves every result for administrator review before prompt injection.
- The console provides simulation prompts, role-card CRUD and preview, project-memory management, initial prompts, approvals, conversation reset, activity, token and estimated-cost records, slang review, and audio-library management. Set input/output cost rates per million tokens to enable cost estimates.

Bridge persistence is separate from the Agent's normal coding sessions. Message transport always goes through Alconna abstractions; features such as native reply references depend on the adapter's exported segment support.

Default web admin panel is on http://127.0.0.1:8080/chat-agent/
## Development checks

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\ruff.exe check --no-cache agent plugin_chatbot tests
.venv\Scripts\pyright.exe agent plugin_chatbot tests
```
