import { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  ArrowRight,
  Bot,
  Check,
  ChevronRight,
  CircleAlert,
  CircleCheck,
  Eye,
  EyeOff,
  Gauge,
  Home,
  KeyRound,
  LayoutList,
  LogOut,
  MessageSquareText,
  Pencil,
  Plug,
  Plus,
  RefreshCw,
  ScrollText,
  Server,
  Settings2,
  ShieldCheck,
  Sparkles,
  Trash2,
  UsersRound,
  X,
} from 'lucide-react';

const NAV = [
  { id: 'overview', label: '运行总览', icon: Home, hint: '节点与服务状态' },
  { id: 'accounts', label: '平台账号', icon: Bot, hint: 'Bot 与人格提示' },
  { id: 'groups', label: '群聊策略', icon: UsersRound, hint: '群级策略覆盖' },
  { id: 'interfaces', label: '接口能力', icon: Plug, hint: '模型与工具目录' },
  { id: 'logs', label: '对话日志', icon: ScrollText, hint: '消息与用量记录' },
];

const emptyInterfaces = { providers: [], skills: [], mcps: [], rules: [] };

function api(token, path, method = 'GET', body) {
  return fetch(`/chat-agent/api${path}`, {
    method,
    headers: { 'content-type': 'application/json', 'x-console-token': token },
    body: body === undefined ? undefined : JSON.stringify(body),
  }).then(async (response) => {
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || `请求失败（${response.status}）`);
    return data;
  });
}

function Login({ onLogin }) {
  const [token, setToken] = useState('');
  const [show, setShow] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    if (!token.trim()) return;
    setBusy(true);
    setError('');
    try {
      await api(token.trim(), '/status');
      sessionStorage.setItem('chatbot-console-token', token.trim());
      onLogin(token.trim());
    } catch (err) {
      setError(err.message || '令牌无效');
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-shell">
      <div className="login-grid-pattern" aria-hidden="true" />
      <section className="login-intro">
        <div className="brand-lockup"><div className="brand-mark"><Sparkles size={21} /></div><div><strong>Chatbot</strong><span>control room</span></div></div>
        <div className="login-copy"><span className="kicker">NONEBOT / ALCONNA</span><h1>让每个账号，<br /><em>拥有自己的节奏。</em></h1><p>跨平台管理 Bot、群聊策略与模型能力。所有运行状态，都在一个安静的工作台里。</p></div>
        <div className="login-foot"><span className="status-dot" />服务端已准备好<span className="login-divider" />v0.1.0</div>
      </section>
      <section className="login-panel">
        <div className="login-panel-inner">
          <div className="login-logo"><ShieldCheck size={23} /></div>
          <span className="kicker">SECURE ACCESS</span>
          <h2>进入控制台</h2>
          <p className="muted">使用控制台访问令牌继续。</p>
          <form onSubmit={submit} className="login-form">
            <label htmlFor="access-token">访问令牌</label>
            <div className="input-wrap"><KeyRound size={17} /><input id="access-token" autoFocus autoComplete="current-password" type={show ? 'text' : 'password'} value={token} onChange={(e) => setToken(e.target.value)} placeholder="输入访问令牌" /><button type="button" className="icon-button" aria-label={show ? '隐藏令牌' : '显示令牌'} onClick={() => setShow((value) => !value)}>{show ? <EyeOff size={17} /> : <Eye size={17} />}</button></div>
            {error && <div className="form-error"><CircleAlert size={15} />{error}</div>}
            <button className="primary-button login-button" disabled={busy || !token.trim()}>{busy ? '验证中…' : <>进入工作台 <ArrowRight size={16} /></>}</button>
          </form>
          <p className="login-note">令牌只保存在当前浏览器会话中。</p>
        </div>
      </section>
    </main>
  );
}

function App() {
  const [token, setToken] = useState(() => sessionStorage.getItem('chatbot-console-token') || '');
  const [page, setPage] = useState('overview');
  const [snapshot, setSnapshot] = useState(null);
  const [error, setError] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  async function refresh() {
    if (!token) return;
    setRefreshing(true);
    try { setSnapshot(await api(token, '/status')); setError(''); } catch (err) { setError(err.message); }
    finally { setRefreshing(false); }
  }

  useEffect(() => { if (token) refresh(); }, [token]);

  if (!token || !snapshot) {
    if (token && error) sessionStorage.removeItem('chatbot-console-token');
    return <Login onLogin={setToken} />;
  }

  const active = NAV.find((item) => item.id === page) || NAV[0];
  const props = { token, snapshot, onRefresh: refresh, onChange: setSnapshot };
  return <div className="app-shell">
    <aside className="sidebar">
      <div className="sidebar-brand"><div className="brand-mark small"><Sparkles size={16} /></div><div><strong>Chatbot</strong><span>control room</span></div></div>
      <div className="sidebar-rule" />
      <div className="sidebar-caption">工作台</div>
      <nav className="sidebar-nav">{NAV.map((item) => { const Icon = item.icon; return <button key={item.id} className={`nav-item ${page === item.id ? 'active' : ''}`} onClick={() => setPage(item.id)}><Icon size={17} /><span>{item.label}</span>{page === item.id && <ChevronRight className="nav-arrow" size={14} />}</button>; })}</nav>
      <div className="sidebar-bottom"><div className="server-status"><span className="status-dot" /><div><strong>服务在线</strong><small>Alconna bridge</small></div></div><button className="logout-button" onClick={() => { sessionStorage.removeItem('chatbot-console-token'); setToken(''); setSnapshot(null); }}><LogOut size={16} />退出</button></div>
    </aside>
    <main className="main-shell">
      <header className="topbar"><div><span className="topbar-kicker">{active.hint}</span><h1>{active.label}</h1></div><div className="topbar-actions"><div className="connection-pill"><span className="status-dot" />已连接</div><button className="refresh-button" onClick={refresh} disabled={refreshing}><RefreshCw size={16} className={refreshing ? 'spin' : ''} />刷新</button></div></header>
      {error && <div className="global-error"><CircleAlert size={16} />{error}</div>}
      <div className="page-content">{page === 'overview' && <Overview {...props} onNavigate={setPage} />}{page === 'accounts' && <Accounts {...props} />}{page === 'groups' && <Groups {...props} />}{page === 'interfaces' && <Interfaces {...props} />}{page === 'logs' && <Logs {...props} />}</div>
    </main>
  </div>;
}

function Overview({ snapshot, onNavigate }) {
  const accounts = snapshot.accounts || []; const groups = snapshot.groups || []; const providers = snapshot.interfaces?.providers || [];
  const online = accounts.filter((item) => item.enabled !== false).length;
  return <div className="page-stack">
    <div className="hero-row"><div><span className="kicker">RUNTIME OVERVIEW</span><h2 className="page-heading">今天的运行状态</h2><p className="muted">账号、群聊和接口能力都在这里保持清晰。</p></div><div className="mode-chip"><Activity size={16} /><span>{snapshot.mode === 'agent' ? 'Agent 模式' : 'Chat 模式'}</span></div></div>
    <div className="metric-grid"><Metric label="运行账号" value={online} detail={`${accounts.length} 个已登记`} icon={Bot} tone="green" /><Metric label="群聊策略" value={groups.length} detail="按账号隔离" icon={UsersRound} tone="blue" /><Metric label="AI 接口" value={providers.length} detail="可自动发现模型" icon={Server} tone="violet" /><Metric label="活动记录" value={(snapshot.activity || []).length} detail="最近 100 条" icon={Gauge} tone="orange" /></div>
    <div className="overview-columns"><section className="surface"><SectionTitle title="账号与群聊" action="管理账号" onClick={() => onNavigate('accounts')} /><div className="account-tree">{accounts.length ? accounts.map((account) => <div className="tree-account" key={account.id}><div className="tree-line"><span className="account-avatar"><Bot size={15} /></span><strong>{account.name || account.bot_id}</strong><span className="soft-tag">{account.platform}</span><span className="tree-meta">{account.bot_id}</span></div><div className="tree-groups">{groups.filter((group) => group.platform === account.platform && group.bot_id === account.bot_id).map((group) => <div className="tree-group" key={group.id}><span className="tree-branch" /><MessageSquareText size={14} /><span>{group.name || group.group_id}</span><small>{group.group_id}</small></div>)}<button className="tree-add" onClick={() => onNavigate('groups')}><Plus size={13} />添加群聊策略</button></div></div>) : <Empty title="还没有账号" detail="收到消息后会自动发现 Bot，也可以从平台账号手动添加。" />}</div></section><section className="surface"><SectionTitle title="最近活动" action="查看日志" onClick={() => onNavigate('logs')} /><div className="activity-list">{(snapshot.activity || []).slice(-7).reverse().map((item, index) => <div className="activity-row" key={`${item.at}-${index}`}><span className="activity-marker"><Activity size={13} /></span><div><strong>{item.text}</strong><small>{formatTime(item.at)}</small></div></div>)}{!(snapshot.activity || []).length && <Empty title="暂无活动" detail="当消息进入桥接后，活动会显示在这里。" />}</div></section></div>
  </div>;
}

function Metric({ label, value, detail, icon: Icon, tone }) { return <div className={`metric-card ${tone}`}><div className="metric-icon"><Icon size={18} /></div><span className="metric-label">{label}</span><strong className="metric-value">{value}</strong><small>{detail}</small></div>; }
function SectionTitle({ title, action, onClick }) { return <div className="section-title"><h3>{title}</h3>{action && <button className="text-button" onClick={onClick}>{action}<ArrowRight size={14} /></button>}</div>; }
function Empty({ title, detail }) { return <div className="empty-state"><div className="empty-icon"><LayoutList size={19} /></div><strong>{title}</strong><span>{detail}</span></div>; }
function formatTime(value) { if (!value) return '刚刚'; return new Date(value * 1000).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }); }
function Status({ enabled = true }) { return <span className={`status-badge ${enabled ? '' : 'disabled'}`}><span />{enabled ? '运行中' : '已停止'}</span>; }

function Accounts({ token, snapshot, onRefresh, onChange }) {
  const [editor, setEditor] = useState(null);
  const accounts = snapshot.accounts || [];
  async function save(body) { const path = editor.id ? `/accounts/${editor.id}` : '/accounts'; const data = await api(token, path, editor.id ? 'PUT' : 'POST', body); onChange({ ...snapshot, accounts: editor.id ? accounts.map((item) => item.id === editor.id ? data : item) : [...accounts, data] }); setEditor(null); }
  async function remove(id) { if (!window.confirm('确认删除这个平台账号？')) return; await api(token, `/accounts/${id}`, 'DELETE'); await onRefresh(); }
  return <div className="page-stack"><PageIntro kicker="PLATFORM ACCOUNTS" title="平台账号" detail="一个 adapter 可以接入多个 Bot。每个账号都拥有独立的插件参数、模型和人格提示。" action="新增账号" onClick={() => setEditor({})} /><section className="surface table-surface"><div className="table-toolbar"><div className="toolbar-label"><Bot size={17} /><span>{accounts.length} 个账号</span></div><span className="muted">账号人格会作为群聊策略的默认提示</span></div><div className="data-table">{accounts.length ? accounts.map((account) => <div className="data-row account-row" key={account.id}><div className="identity-cell"><span className="account-avatar large"><Bot size={18} /></span><div><strong>{account.name || account.bot_id}</strong><small>{account.platform} · {account.bot_id}</small></div></div><div><span className="cell-label">插件</span><span>{account.plugin || account.platform}</span></div><div><span className="cell-label">群聊</span><span>{(snapshot.groups || []).filter((group) => group.platform === account.platform && group.bot_id === account.bot_id).length} 个策略</span></div><Status enabled={account.enabled !== false} /><div className="row-actions"><button className="icon-button" title="编辑账号" onClick={() => setEditor(account)}><Pencil size={15} /></button><button className="icon-button danger" title="删除账号" onClick={() => remove(account.id)}><Trash2 size={15} /></button></div></div>) : <Empty title="还没有平台账号" detail="可以等待消息自动发现，也可以立即新增一个账号。" />}</div></section>{editor && <AccountEditor value={editor} onClose={() => setEditor(null)} onSave={save} />}</div>;
}

function PageIntro({ kicker, title, detail, action, onClick }) { return <div className="page-intro"><div><span className="kicker">{kicker}</span><h2 className="page-heading">{title}</h2><p className="muted intro-detail">{detail}</p></div>{action && <button className="primary-button" onClick={onClick}><Plus size={16} />{action}</button>}</div>; }
function AccountEditor({ value, onClose, onSave }) { const [form, setForm] = useState({ enabled: true, reasoning_effort: 'medium', plugin_config: '{}', ...value }); const set = (key, next) => setForm((prev) => ({ ...prev, [key]: next })); return <Modal title={value.id ? '编辑平台账号' : '新增平台账号'} onClose={onClose}><div className="form-grid two"><Field label="账号名称" value={form.name || ''} onChange={(v) => set('name', v)} placeholder="例如：主账号" /><Field label="平台 / adapter" value={form.platform || ''} onChange={(v) => set('platform', v)} placeholder="onebot / qq / satori" /><Field label="Bot ID" value={form.bot_id || ''} onChange={(v) => set('bot_id', v)} /><Field label="插件标识" value={form.plugin || ''} onChange={(v) => set('plugin', v)} /><Field label="模型" value={form.model || ''} onChange={(v) => set('model', v)} /><Field label="Base URL" value={form.base_url || ''} onChange={(v) => set('base_url', v)} /><Field label="API Key" type="password" value={form.api_key || ''} onChange={(v) => set('api_key', v)} /><SelectField label="思考强度" value={form.reasoning_effort || 'medium'} options={['low', 'medium', 'high']} onChange={(v) => set('reasoning_effort', v)} /><Field label="人格提示" wide type="textarea" value={form.persona_prompt || ''} onChange={(v) => set('persona_prompt', v)} placeholder="这个账号默认如何说话、如何称呼用户？" /><Field label="插件参数 JSON" wide type="textarea" value={typeof form.plugin_config === 'string' ? form.plugin_config : JSON.stringify(form.plugin_config || {}, null, 2)} onChange={(v) => set('plugin_config', v)} /></div><ModalFooter onClose={onClose} onSave={() => { let config = {}; try { config = JSON.parse(form.plugin_config || '{}'); } catch { window.alert('插件参数 JSON 无效'); return; } onSave({ ...form, plugin_config: config, enabled: form.enabled !== false }); }} /></Modal>; }

function Groups({ token, snapshot, onRefresh, onChange }) { const [editor, setEditor] = useState(null); const groups = snapshot.groups || []; const accounts = snapshot.accounts || []; const providers = snapshot.interfaces?.providers || []; async function save(body) { const path = editor.id ? `/groups/${editor.id}` : '/groups'; const data = await api(token, path, editor.id ? 'PUT' : 'POST', body); onChange({ ...snapshot, groups: editor.id ? groups.map((item) => item.id === editor.id ? data : item) : [...groups, data] }); setEditor(null); } async function remove(id) { if (!window.confirm('确认删除这个群聊策略？')) return; await api(token, `/groups/${id}`, 'DELETE'); await onRefresh(); } return <div className="page-stack"><PageIntro kicker="GROUP POLICIES" title="群聊策略" detail="在这里覆盖账号默认设置。每个群聊可以选择自己的供应商、模型、提示词、回复频率与工具集合。" action="添加策略" onClick={() => setEditor({})} /><section className="surface table-surface"><div className="table-toolbar"><div className="toolbar-label"><UsersRound size={17} /><span>{groups.length} 个群聊策略</span></div><span className="muted">群 ID 与 Bot ID 一起决定策略作用范围</span></div><div className="data-table">{groups.length ? groups.map((group) => <div className="data-row" key={group.id}><div className="identity-cell"><span className="group-avatar"><MessageSquareText size={17} /></span><div><strong>{group.name || group.group_id}</strong><small>{group.platform} / {group.bot_id} · {group.group_id}</small></div></div><div><span className="cell-label">供应商</span><span>{providers.find((item) => item.id === group.provider_id)?.name || '跟随账号'}</span></div><div><span className="cell-label">模型</span><span>{group.model || '账号默认'}</span></div><div><span className="cell-label">频率</span><span>{group.reply_frequency || 'balanced'}</span></div><Status enabled={group.enabled !== false} /><div className="row-actions"><button className="icon-button" title="编辑策略" onClick={() => setEditor(group)}><Pencil size={15} /></button><button className="icon-button danger" title="删除策略" onClick={() => remove(group.id)}><Trash2 size={15} /></button></div></div>) : <Empty title="还没有群聊策略" detail="先添加账号，再为账号绑定群聊 ID。" />}</div></section>{editor && <GroupEditor value={editor} accounts={accounts} providers={providers} catalogs={snapshot.interfaces || emptyInterfaces} onClose={() => setEditor(null)} onSave={save} />}</div>; }

function GroupEditor({ value, accounts, providers, catalogs, onClose, onSave }) { const first = accounts.find((item) => item.platform === value.platform && item.bot_id === value.bot_id); const [form, setForm] = useState({ enabled: true, reply_frequency: 'balanced', reasoning_effort: 'medium', tools: { skills: [], mcps: [], rules: [] }, ...value, account: first ? `${first.platform} / ${first.bot_id}` : '' }); const set = (key, next) => setForm((prev) => ({ ...prev, [key]: next })); const accountByLabel = accounts.find((item) => `${item.platform} / ${item.bot_id}` === form.account); const toggleTool = (kind, id) => set('tools', { ...form.tools, [kind]: form.tools?.[kind]?.includes(id) ? form.tools[kind].filter((item) => item !== id) : [...(form.tools?.[kind] || []), id] }); return <Modal title={value.id ? '编辑群聊策略' : '添加群聊策略'} onClose={onClose}><div className="form-grid two"><SelectField label="绑定账号" value={form.account} options={accounts.map((item) => `${item.platform} / ${item.bot_id}`)} onChange={(v) => set('account', v)} /><Field label="群 ID" value={form.group_id || ''} onChange={(v) => set('group_id', v)} /><Field label="群名称" value={form.name || ''} onChange={(v) => set('name', v)} placeholder="可选，无法获取时使用群 ID" /><SelectField label="AI 供应商" value={form.provider_id || ''} options={['', ...providers.map((item) => item.id)]} onChange={(v) => set('provider_id', v)} /><Field label="模型" value={form.model || ''} onChange={(v) => set('model', v)} placeholder="留空则跟随账号" /><SelectField label="回复频率" value={form.reply_frequency || 'balanced'} options={['quiet', 'balanced', 'active']} onChange={(v) => set('reply_frequency', v)} /><SelectField label="思考强度" value={form.reasoning_effort || 'medium'} options={['low', 'medium', 'high']} onChange={(v) => set('reasoning_effort', v)} /><Field label="成本上限" type="number" value={form.cost_limit ?? ''} onChange={(v) => set('cost_limit', v)} /><Field label="群聊提示词" wide type="textarea" value={form.system_prompt || ''} onChange={(v) => set('system_prompt', v)} placeholder="留空则继承账号人格提示" /></div><div className="tool-pickers"><ToolPicker title="Skill" kind="skills" rows={catalogs.skills || []} selected={form.tools?.skills || []} onToggle={toggleTool} /><ToolPicker title="MCP" kind="mcps" rows={catalogs.mcps || []} selected={form.tools?.mcps || []} onToggle={toggleTool} /><ToolPicker title="Rules" kind="rules" rows={catalogs.rules || []} selected={form.tools?.rules || []} onToggle={toggleTool} /></div><ModalFooter onClose={onClose} onSave={() => onSave({ ...form, platform: accountByLabel?.platform || value.platform || '', bot_id: accountByLabel?.bot_id || value.bot_id || '', enabled: form.enabled !== false })} /></Modal>; }
function ToolPicker({ title, kind, rows, selected, onToggle }) { return <div className="tool-picker"><div className="tool-picker-head"><strong>{title}</strong><span>{selected.length} 已选</span></div>{rows.length ? rows.map((row) => <label key={row.id} className="check-row"><input type="checkbox" checked={selected.includes(row.id)} onChange={() => onToggle(kind, row.id)} /><span>{row.name || row.id}</span></label>) : <span className="muted">暂无可用项</span>}</div>; }

function Interfaces({ token, snapshot, onRefresh, onChange }) { const [tab, setTab] = useState('providers'); const [editor, setEditor] = useState(null); const rows = snapshot.interfaces?.[tab] || []; async function save(body) { const path = `/interfaces/${tab}${editor.id ? `/${editor.id}` : ''}`; const data = await api(token, path, editor.id ? 'PUT' : 'POST', body); onChange({ ...snapshot, interfaces: { ...snapshot.interfaces, [tab]: editor.id ? rows.map((item) => item.id === editor.id ? data : item) : [...rows, data] } }); setEditor(null); } async function remove(id) { if (!window.confirm('确认删除这个能力？')) return; await api(token, `/interfaces/${tab}/${id}`, 'DELETE'); await onRefresh(); } async function discover(id) { try { const result = await api(token, `/interfaces/providers/${id}/models`, 'POST'); onChange({ ...snapshot, interfaces: { ...snapshot.interfaces, providers: (snapshot.interfaces.providers || []).map((item) => item.id === id ? { ...item, models: result.models } : item) } }); } catch (err) { window.alert(err.message); } } return <div className="page-stack"><PageIntro kicker="INTERFACE CAPABILITIES" title="接口能力" detail="统一管理 OpenAI-compatible 接口，以及群聊可以勾选的 Skill、MCP 和 Rules。" action="新增能力" onClick={() => setEditor({})} /><section className="surface"><div className="tabs">{[['providers', 'AI 接口'], ['skills', 'Skill'], ['mcps', 'MCP'], ['rules', 'Rules']].map(([id, label]) => <button key={id} className={tab === id ? 'active' : ''} onClick={() => setTab(id)}>{label}</button>)}</div><div className="data-table">{rows.length ? rows.map((row) => <div className="data-row" key={row.id}><div className="identity-cell"><span className="capability-icon"><Plug size={16} /></span><div><strong>{row.name || row.id}</strong><small>{row.base_url || row.url || row.description || row.content || '尚未填写描述'}</small></div></div><div><span className="cell-label">{tab === 'providers' ? '模型' : '类型'}</span><span>{tab === 'providers' ? (row.models?.length || row.model || '未发现') : tab.toUpperCase()}</span></div><div className="row-actions">{tab === 'providers' && <button className="soft-button" onClick={() => discover(row.id)}><RefreshCw size={14} />拉取模型</button>}<button className="icon-button" onClick={() => setEditor(row)} title="编辑"><Pencil size={15} /></button><button className="icon-button danger" onClick={() => remove(row.id)} title="删除"><Trash2 size={15} /></button></div></div>) : <Empty title="还没有接口能力" detail="先添加一个 AI 接口，群聊策略才能选择模型和工具。" />}</div></section>{editor && <CapabilityEditor kind={tab} value={editor} onClose={() => setEditor(null)} onSave={save} />}</div>; }
function CapabilityEditor({ kind, value, onClose, onSave }) { const [form, setForm] = useState(value); const labels = { providers: ['接口名称', 'Base URL', '默认模型', 'API Key'], skills: ['Skill 名称', '描述'], mcps: ['MCP 名称', '服务地址'], rules: ['Rule 名称', '规则内容'] }[kind]; return <Modal title={value.id ? '编辑接口能力' : '新增接口能力'} onClose={onClose}><div className="form-grid"><Field label={labels[0]} value={form.name || ''} onChange={(v) => setForm({ ...form, name: v })} />{kind === 'providers' ? <><Field label={labels[1]} value={form.base_url || ''} onChange={(v) => setForm({ ...form, base_url: v })} /><Field label={labels[2]} value={form.model || ''} onChange={(v) => setForm({ ...form, model: v })} /><Field label={labels[3]} type="password" value={form.api_key || ''} onChange={(v) => setForm({ ...form, api_key: v })} /></> : <Field label={labels[1]} wide type="textarea" value={form.description || form.url || form.content || ''} onChange={(v) => setForm({ ...form, [kind === 'mcps' ? 'url' : kind === 'rules' ? 'content' : 'description']: v })} />}</div><ModalFooter onClose={onClose} onSave={() => onSave(form)} /></Modal>; }

function Logs({ token, snapshot }) { const [logs, setLogs] = useState({ activity: snapshot.activity || [], usage: snapshot.usage || [] }); useEffect(() => { api(token, '/logs').then(setLogs).catch(() => {}); }, [token]); return <div className="page-stack"><PageIntro kicker="CONVERSATION LOG" title="对话日志" detail="查看桥接活动、会话映射和模型用量，帮助定位消息与策略问题。" /><div className="logs-grid"><section className="surface"><SectionTitle title="活动流" /><div className="log-list">{logs.activity.length ? logs.activity.slice().reverse().map((item, index) => <div className="log-row" key={`${item.at}-${index}`}><span className="log-time">{formatTime(item.at)}</span><span>{item.text}</span></div>) : <Empty title="暂无活动记录" detail="收到消息后会显示事件摘要。" />}</div></section><section className="surface"><SectionTitle title="用量记录" /><div className="usage-list">{logs.usage.length ? logs.usage.slice().reverse().slice(0, 12).map((item, index) => <div className="usage-row" key={`${item.at}-${index}`}><div><strong>{item.conversation?.slice(0, 10) || 'session'}</strong><small>{formatTime(item.at)}</small></div><span>{item.total || 0} tokens</span><b>${Number(item.estimated_cost || 0).toFixed(4)}</b></div>) : <Empty title="暂无用量记录" detail="模型调用后会显示 token 与估算成本。" />}</div></section></div></div>; }

function Modal({ title, onClose, children }) { return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}><div className="modal"><div className="modal-head"><div><span className="kicker">CONFIGURATION</span><h2>{title}</h2></div><button className="icon-button" onClick={onClose} aria-label="关闭"><X size={17} /></button></div>{children}</div></div>; }
function ModalFooter({ onClose, onSave }) { return <div className="modal-footer"><button className="secondary-button" onClick={onClose}>取消</button><button className="primary-button" onClick={onSave}><Check size={15} />保存设置</button></div>; }
function Field({ label, value, onChange, placeholder, type = 'text', wide = false }) { return <label className={`field ${wide ? 'wide' : ''}`}><span>{label}</span>{type === 'textarea' ? <textarea value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} /> : <input type={type} value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} />}</label>; }
function SelectField({ label, value, options, onChange }) { return <label className="field"><span>{label}</span><select value={value} onChange={(e) => onChange(e.target.value)}>{options.map((option) => <option key={option} value={option}>{option || '默认'}</option>)}</select></label>; }

export default App;
