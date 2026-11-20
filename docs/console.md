# 管理后台

后台挂载在 NoneBot 既有的 FastAPI 服务器上，默认地址为：

<http://127.0.0.1:8080/chat-agent/>

令牌即 `BRIDGE_CONSOLE_TOKEN`；没有配置时，插件会生成一份并保存到状态目录下的 `console-token` 文件。

## 首次使用

1. 在 **接口能力** 里配置模型连接（Provider 与模型）。
2. 在 **平台账号** 里选好 Provider 与模型，配置管理员、白名单、黑名单。
3. 在 **群聊策略** 里按群设置回复概率、提示词与启用工具。
4. 会话第一次被发现时处于 **待确认** 状态，需要管理员批准或加进白名单才会响应。

## 页面一览

侧边栏分两组：**工作台**（运行总览、平台账号、人格提示、群聊策略、接口能力）与 **数据与记录**（记忆管理、表情包、对话日志）。

| 页面 | 内容 |
| --- | --- |
| 运行总览 | 活跃度、token 与成本估算、最近活动、连接状态。 |
| 平台账号 | Bot 账号的 Provider / 模型、推理强度、人格模板与补充提示词、工具开关、管理员与白名单、禁用自称清单。 |
| 人格提示 | 可复用的角色卡模板、初始提示词、审批设置。 |
| 群聊策略 | 按群的回复概率、提示词覆盖、模型与成本上限、工具开关。 |
| 接口能力 | Provider、技能、MCP 服务器、规则、自定义 Tool、运行时工具目录。Provider 的 API Key 只回显末 4 位；编辑时留空即保持不变，需要替换或清除请在表单里显式操作。 |
| 记忆管理 | 全局记忆条目的增删改，群黑话词库与自动复核配置。 |
| 表情包 | 词库列表（鉴权缩略图）、名称 / 关键词 / 摘要编辑、上传与删除。 |
| 对话日志 | 消息日志、人格漂移命中记录、按群或按私聊的会话转录（带清空按钮）。 |

会话表还允许管理员按会话挑选启用哪些工具。新会话默认启用当前模式下的全部工具，切换模式会清掉会话级覆盖。

## 构建前端

后台界面是独立的 `webui/` 项目，它的源码与 Node 依赖只用于开发；Python 包里只包含生成后的静态文件 `plugin_chatbot/plugins/webui/`。运行后台之前先构建：

```powershell
cd webui
npm install
npm run build
```

`npm run build` 会把 Vite 产物从 `webui/dist/` 复制到 `plugin_chatbot/plugins/webui/`，插件再把这个打包目录挂到 `/chat-agent/`。

## 开发调试

```powershell
cd webui
npm run dev
```

开发服务器监听 `http://localhost:5178/`，并把 `/chat-agent` 代理到正在运行的 NoneBot 服务（默认 `http://127.0.0.1:8080`，可用 `CHATBOT_BACKEND` 覆盖），改动不必重新构建就能拿到实时接口数据。

## 前端结构

前端是 Vite + React 应用，组织为一套小型设计系统加若干功能页面：

```
webui/src/
  styles/           设计令牌、基础层、动效、表单与列表排版
  lib/              API 客户端、导航定义、纯函数格式化
  hooks/            useCountUp 等无副作用 hook
  components/ui/    Button / Card / Field / Modal / Tabs / DataTable / Badge …
  components/layout/ 外壳、侧边栏、上下文栏
  components/feedback/ 提示与确认浮层
  pages/            每个页面一个目录，页面私有的编辑器与样式就近放置
```

## 视觉规范

视觉语言沿用 StyleKit 的 `soft-ui` 方向：16 / 24 px 圆角、低饱和配色、带色相的柔和阴影、300–500 ms 动效，不使用 1 px 硬边框。令牌集中在 `src/styles/tokens.css`，改色改间距请改令牌，不要在组件里硬编码颜色。所有动效在 `prefers-reduced-motion` 下自动关闭。
