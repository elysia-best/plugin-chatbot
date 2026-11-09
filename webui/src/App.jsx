import { useEffect, useRef, useState } from 'react';
import {
  Activity, ArrowRight, Bot, Check, ChevronRight, CircleAlert, Eye, EyeOff,
  BookOpen, Gauge, Home, Image as ImageIcon, KeyRound, LayoutList, LogOut,
  MessageCircle, MessageSquareText, Pencil, Plug, Plus, RefreshCw, ScrollText,
  Server, ShieldCheck, Sparkles, Trash2, Upload, UsersRound, Wrench, X,
} from 'lucide-react';

const NAV = [
  { id: 'overview', label: '运行总览', icon: Home, hint: '节点与服务状态' },
  { id: 'accounts', label: '平台账号', icon: Bot, hint: 'Bot 与账号策略' },
  { id: 'personas', label: '人格提示', icon: Sparkles, hint: '人格模板工作台' },
  { id: 'groups', label: '群聊策略', icon: UsersRound, hint: '群级策略覆盖' },
  { id: 'interfaces', label: '接口能力', icon: Plug, hint: '模型与工具目录' },
  { id: 'memory', label: '记忆管理', icon: BookOpen, hint: '全局 Memory 与黑话' },
  { id: 'memes', label: '表情包', icon: ImageIcon, hint: '表情包库与工具' },
  { id: 'logs', label: '对话日志', icon: ScrollText, hint: '消息与用量记录' },
];

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

async function apiBlob(token, path) {
  const response = await fetch(`/chat-agent/api${path}`, {
    headers: { 'x-console-token': token },
  });
  if (!response.ok) throw new Error(`请求失败（${response.status}）`);
  return response.blob();
}

function Login({ onLogin }) {
  const [token, setToken] = useState(''); const [show, setShow] = useState(false);
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  async function submit(event) {
    event.preventDefault(); if (!token.trim()) return; setBusy(true); setError('');
    try { await api(token.trim(), '/status'); sessionStorage.setItem('chatbot-console-token', token.trim()); onLogin(token.trim()); }
    catch (err) { setError(err.message || '令牌无效'); } finally { setBusy(false); }
  }
  return <main className="login-shell"><div className="login-grid-pattern" aria-hidden="true" /><section className="login-intro"><div className="brand-lockup"><div className="brand-mark"><Sparkles size={21} /></div><div><strong>Chatbot</strong><span>control room</span></div></div><div className="login-copy"><span className="kicker">NONEBOT / ALCONNA</span><h1>让每个账号，<br /><em>拥有自己的节奏。</em></h1><p>跨平台管理 Bot、人格、群聊策略与模型能力。</p></div><div className="login-foot"><span className="status-dot" />服务端已准备好<span className="login-divider" />v0.1.0</div></section><section className="login-panel"><div className="login-panel-inner"><div className="login-logo"><ShieldCheck size={23} /></div><span className="kicker">SECURE ACCESS</span><h2>进入控制台</h2><p className="muted">使用控制台访问令牌继续。</p><form onSubmit={submit} className="login-form"><label htmlFor="access-token">访问令牌</label><div className="input-wrap"><KeyRound size={17} /><input id="access-token" autoFocus autoComplete="current-password" type={show ? 'text' : 'password'} value={token} onChange={(e) => setToken(e.target.value)} placeholder="输入访问令牌" /><button type="button" className="icon-button" aria-label={show ? '隐藏令牌' : '显示令牌'} onClick={() => setShow(!show)}>{show ? <EyeOff size={17} /> : <Eye size={17} />}</button></div>{error && <div className="form-error"><CircleAlert size={15} />{error}</div>}<button className="primary-button login-button" disabled={busy || !token.trim()}>{busy ? '验证中…' : <>进入工作台 <ArrowRight size={16} /></>}</button></form><p className="login-note">令牌只保存在当前浏览器会话中。</p></div></section></main>;
}

function App() {
  const [token, setToken] = useState(() => sessionStorage.getItem('chatbot-console-token') || '');
  const [page, setPage] = useState('overview'); const [snapshot, setSnapshot] = useState(null);
  const [roles, setRoles] = useState({ roles: [], active: null }); const [tools, setTools] = useState([]);
  const [error, setError] = useState(''); const [refreshing, setRefreshing] = useState(false);
  async function refresh() {
    if (!token) return; setRefreshing(true);
    try { const [next, roleRows, toolRows] = await Promise.all([api(token, '/status'), api(token, '/roles'), api(token, '/tools')]); setSnapshot(next); setRoles(roleRows); setTools(toolRows); setError(''); }
    catch (err) { setError(err.message); } finally { setRefreshing(false); }
  }
  useEffect(() => { if (token) refresh(); }, [token]);
  if (!token || !snapshot) { if (token && error) sessionStorage.removeItem('chatbot-console-token'); return <Login onLogin={setToken} />; }
  const active = NAV.find((item) => item.id === page) || NAV[0];
  const props = { token, snapshot, roles, tools, onRefresh: refresh, onRolesChange: setRoles, onNavigate: setPage };
  return <div className="app-shell"><aside className="sidebar"><div className="sidebar-brand"><div className="brand-mark small"><Sparkles size={16} /></div><div><strong>Chatbot</strong><span>control room</span></div></div><div className="sidebar-rule" /><div className="sidebar-caption">工作台</div><nav className="sidebar-nav">{NAV.map((item) => { const Icon = item.icon; return <button key={item.id} className={`nav-item ${page === item.id ? 'active' : ''}`} onClick={() => setPage(item.id)}><Icon size={17} /><span>{item.label}</span>{page === item.id && <ChevronRight className="nav-arrow" size={14} />}</button>; })}</nav><div className="sidebar-bottom"><div className="server-status"><span className="status-dot" /><div><strong>服务在线</strong><small>Alconna bridge</small></div></div><button className="logout-button" onClick={() => { sessionStorage.removeItem('chatbot-console-token'); setToken(''); setSnapshot(null); }}><LogOut size={16} />退出</button></div></aside><main className="main-shell"><header className="topbar"><div><span className="topbar-kicker">{active.hint}</span><h1>{active.label}</h1></div><div className="topbar-actions"><div className="connection-pill"><span className="status-dot" />已连接</div><button className="refresh-button" onClick={refresh} disabled={refreshing}><RefreshCw size={16} className={refreshing ? 'spin' : ''} />刷新</button></div></header>{error && <div className="global-error"><CircleAlert size={16} />{error}</div>}<div className="page-content">{page === 'overview' && <Overview {...props} onNavigate={setPage} />}{page === 'accounts' && <Accounts {...props} />}{page === 'personas' && <Personas {...props} />}{page === 'groups' && <Groups {...props} />}{page === 'interfaces' && <Interfaces {...props} />}{page === 'memory' && <Memory {...props} />}{page === 'memes' && <Memes {...props} />}{page === 'logs' && <Logs {...props} />}</div></main></div>;
}

function Overview({ snapshot, onNavigate }) {
  const accounts = snapshot.accounts || []; const groups = snapshot.groups || []; const providers = snapshot.interfaces?.providers || [];
  return <div className="page-stack"><div className="hero-row"><div><span className="kicker">RUNTIME OVERVIEW</span><h2 className="page-heading">今天的运行状态</h2><p className="muted">账号、群聊、人格和接口能力都在这里保持清晰。</p></div><div className="mode-chip"><Activity size={16} />{snapshot.mode === 'agent' ? 'Agent 模式' : 'Chat 模式'}</div></div><div className="metric-grid"><Metric label="运行账号" value={accounts.filter((x) => x.enabled !== false).length} detail={`${accounts.length} 个已登记`} icon={Bot} tone="green" /><Metric label="群聊策略" value={groups.length} detail="按账号隔离" icon={UsersRound} tone="blue" /><Metric label="AI 接口" value={providers.length} detail="可自动发现模型" icon={Server} tone="violet" /><Metric label="活动记录" value={(snapshot.activity || []).length} detail="最近 100 条" icon={Gauge} tone="orange" /></div><div className="overview-columns"><section className="surface"><SectionTitle title="账号与群聊" action="管理账号" onClick={() => onNavigate('accounts')} /><div className="account-tree">{accounts.length ? accounts.map((account) => <div className="tree-account" key={account.id}><div className="tree-line"><span className="account-avatar"><Bot size={15} /></span><strong>{account.name || account.bot_id}</strong><span className="soft-tag">{account.platform}</span><span className="tree-meta">{account.bot_id}</span></div><div className="tree-groups">{groups.filter((g) => g.platform === account.platform && g.bot_id === account.bot_id).map((group) => <div className="tree-group" key={group.id}><span className="tree-branch" /><MessageSquareText size={14} /><span>{group.name || group.group_id}</span><small>{group.group_id}</small></div>)}<button className="tree-add" onClick={() => onNavigate('groups')}><Plus size={13} />添加群聊策略</button></div></div>) : <Empty title="还没有账号" detail="收到消息后会自动发现 Bot，也可以手动添加。" />}</div></section><section className="surface"><SectionTitle title="最近活动" action="查看日志" onClick={() => onNavigate('logs')} /><div className="activity-list">{(snapshot.activity || []).slice(-7).reverse().map((item, index) => <div className="activity-row" key={`${item.at}-${index}`}><span className="activity-marker"><Activity size={13} /></span><div><strong>{item.text}</strong><small>{formatTime(item.at)}</small></div></div>)}{!(snapshot.activity || []).length && <Empty title="暂无活动" detail="当消息进入桥接后，活动会显示在这里。" />}</div></section></div></div>;
}
function Metric({ label, value, detail, icon: Icon, tone }) { return <div className={`metric-card ${tone}`}><div className="metric-icon"><Icon size={18} /></div><span className="metric-label">{label}</span><strong className="metric-value">{value}</strong><small>{detail}</small></div>; }
function SectionTitle({ title, action, onClick }) { return <div className="section-title"><h3>{title}</h3>{action && <button className="text-button" onClick={onClick}>{action}<ArrowRight size={14} /></button>}</div>; }
function Empty({ title, detail }) { return <div className="empty-state"><div className="empty-icon"><LayoutList size={19} /></div><strong>{title}</strong><span>{detail}</span></div>; }
function formatTime(value) { return value ? new Date(value * 1000).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '刚刚'; }
function Status({ enabled = true }) { return <span className={`status-badge ${enabled ? '' : 'disabled'}`}><span />{enabled ? '运行中' : '已停止'}</span>; }
function modelId(model) { return typeof model === 'string' ? model : model?.id || ''; }
function modelContext(model) { return typeof model === 'object' ? model.context_length : null; }
function providerLabel(provider) { return provider ? (provider.name || provider.base_url || provider.id || '未命名接口') : ''; }

function Accounts({ token, snapshot, roles, tools, onRefresh }) {
  const [editor, setEditor] = useState(null); const accounts = snapshot.accounts || []; const providers = snapshot.interfaces?.providers || [];
  async function save(body) { const { admins = [], whitelist = [], blacklist = [], ...accountBody } = body; const saved = await api(token, editor.id ? `/accounts/${editor.id}` : '/accounts', editor.id ? 'PUT' : 'POST', accountBody); if (!editor.id) setEditor((current) => ({ ...current, id: saved.id })); await api(token, `/accounts/${saved.id}/access`, 'PUT', { admins, whitelist, blacklist }); await onRefresh(); setEditor(null); }
  async function remove(id) { if (!window.confirm('确认删除这个平台账号？')) return; await api(token, `/accounts/${id}`, 'DELETE'); await onRefresh(); }
  return <div className="page-stack"><PageIntro kicker="PLATFORM ACCOUNTS" title="平台账号" detail="每个 Bot 都拥有独立的接口、人格和工具默认值。名称来自 adapter 时会优先展示昵称。" action="新增账号" onClick={() => setEditor({})} /><section className="surface table-surface"><div className="table-toolbar"><div className="toolbar-label"><Bot size={17} /><span>{accounts.length} 个账号</span></div><span className="muted">ID 保留用于精确定位</span></div><div className="data-table">{accounts.length ? accounts.map((account) => { const provider = providers.find((p) => p.id === account.provider_id); return <div className="data-row account-row" key={account.id}><div className="identity-cell"><span className="account-avatar large"><Bot size={18} /></span><div><strong>{account.name || account.bot_id}</strong><small>{account.platform} · {account.bot_id}</small></div></div><div><span className="cell-label">AI 接口</span><span>{providerLabel(provider) || '未选择接口'}</span></div><div><span className="cell-label">群聊</span><span>{(snapshot.groups || []).filter((g) => g.platform === account.platform && g.bot_id === account.bot_id).length} 个策略</span></div><Status enabled={account.enabled !== false} /><div className="row-actions"><button className="icon-button" title="编辑账号" onClick={() => setEditor(account)}><Pencil size={15} /></button><button className="icon-button danger" title="删除账号" onClick={() => remove(account.id)}><Trash2 size={15} /></button></div></div>; }) : <Empty title="还没有平台账号" detail="可以等待消息自动发现，也可以立即新增一个账号。" />}</div></section>{editor && <AccountEditor value={editor} roles={roles.roles} tools={tools} providers={providers} snapshot={snapshot} onClose={() => setEditor(null)} onSave={save} />}</div>;
}

function AccountEditor({ value, roles, tools, providers, snapshot, onClose, onSave }) {
  const [form, setForm] = useState({ enabled: true, reasoning_effort: 'medium', temperature_enabled: true, temperature: 0.7, persona_role: '', provider_id: '', enabled_tools: null, ...value }); const [saving, setSaving] = useState(false); const [saveError, setSaveError] = useState(''); const set = (key, next) => setForm((p) => ({ ...p, [key]: next }));
  const provider = providers.find((p) => p.id === form.provider_id); const models = provider?.models || [];
  const selectProvider = (providerId) => { const nextProvider = providers.find((p) => p.id === providerId); const currentModel = modelId(form.model); const nextModel = nextProvider?.models?.some((m) => m.id === currentModel) ? currentModel : modelId(nextProvider?.model); setForm((p) => ({ ...p, provider_id: providerId, model: nextModel })); };
  async function submit() {
    setSaving(true); setSaveError('');
    try {
      const { base_url: _baseUrl, api_key: _apiKey, ...payload } = form;
      await onSave({ ...payload, provider_id: form.provider_id || '', model: modelId(form.model), context_length: Number(form.context_length) || null, enabled: form.enabled !== false });
    } catch (error) { setSaveError(error.message || '账号设置保存失败'); }
    finally { setSaving(false); }
  }
  return <Modal title={value.id ? '编辑平台账号' : '新增平台账号'} onClose={onClose}><div className="form-grid two"><Field label="账号名称" value={form.name || ''} onChange={(v) => set('name', v)} placeholder="留空则使用 Bot ID" /><Field label="平台 / adapter" value={form.platform || ''} onChange={(v) => set('platform', v)} placeholder="onebot / qq / satori" /><Field label="Bot ID" value={form.bot_id || ''} onChange={(v) => set('bot_id', v)} /><SelectField label="AI 接口" value={form.provider_id || ''} options={['', ...providers.map((p) => p.id)]} labels={['选择已配置接口', ...providers.map(providerLabel)]} onChange={selectProvider} /><SelectField label="模型" value={modelId(form.model)} options={['', ...models.map((m) => m.id)]} labels={['使用接口默认模型', ...models.map((m) => `${m.id}${modelContext(m) ? ` · ${modelContext(m).toLocaleString()} tokens` : ''}`)]} onChange={(v) => set('model', v)} /><SelectField label="思考强度" value={form.reasoning_effort || 'medium'} options={['low', 'medium', 'high']} onChange={(v) => set('reasoning_effort', v)} /><Field label="Temperature（0–2）" type="number" value={form.temperature ?? 0.7} onChange={(v) => set('temperature', v)} placeholder="默认 0.7" /><label className="check-row wide"><input type="checkbox" checked={form.temperature_enabled !== false} onChange={(event) => set('temperature_enabled', event.target.checked)} />启用 Temperature 参数（不兼容模型请关闭）</label><Field label="备用上下文大小" type="number" value={form.context_length || ''} onChange={(v) => set('context_length', v)} placeholder="接口模型没有提供时使用" /><div className="field wide"><span>接口上下文</span><span className="muted">{modelContext(models.find((m) => m.id === modelId(form.model))) ? `当前模型：${modelContext(models.find((m) => m.id === modelId(form.model))).toLocaleString()} tokens（远端识别）` : provider ? '当前模型未提供上下文，将使用备用设置或全局设置。' : '请先在接口能力中配置 AI 接口。'}</span></div><SelectField label="人格模板" value={form.persona_role || ''} options={['', ...roles.map((r) => r.name)]} labels={['全局默认', ...roles.map((r) => r.name)]} onChange={(v) => set('persona_role', v)} /><Field label="账号补充提示" wide type="textarea" value={form.persona_prompt || ''} onChange={(v) => set('persona_prompt', v)} placeholder="追加在人格模板之后的说话规则" /><Field label="禁用称谓 / 口癖黑名单（换行或逗号分隔）" wide type="textarea" value={Array.isArray(form.persona_banned) ? form.persona_banned.join('\n') : (form.persona_banned || '')} onChange={(v) => set('persona_banned', v.split(/[\n,，、]+/).map((item) => item.trim()).filter(Boolean))} placeholder="例如：本鲸（其他 Bot 的自称）。命中时丢弃该条回复并重试一次" /><label className="check-row wide"><input type="checkbox" checked={form.memory_enabled !== false} onChange={(event) => set('memory_enabled', event.target.checked)} />为此 Bot 自动整理记忆草稿</label><Field label="每收到多少条消息后总结" type="number" value={form.memory_interval ?? 50} onChange={(v) => set('memory_interval', v)} placeholder="默认 50，范围 1–1000" /></div><ToolSelection value={form.enabled_tools} tools={tools} onChange={(v) => set('enabled_tools', v)} /><AccessLists value={form} snapshot={snapshot} onChange={(patch) => setForm((p) => ({ ...p, ...patch }))} />{saveError && <div className="form-error"><CircleAlert size={15} />{saveError}</div>}<ModalFooter onClose={onClose} onSave={submit} busy={saving} /></Modal>;
}

function AccessLists({ value, snapshot, onChange }) {
  const [filter, setFilter] = useState(''); const [draft, setDraft] = useState({ id: '', name: '', kind: 'private', list: 'whitelist' });
  const conversations = snapshot?.conversations || []; const groups = snapshot?.groups || [];
  const rawUsers = Array.isArray(value.private_users) ? value.private_users : [];
  const users = rawUsers.map((item) => typeof item === 'object' && item ? { ...item, id: String(item.id || '') } : { id: String(item || ''), name: '' }).filter((item) => item.id);
  const sameAccount = (row) => String(row.platform || row.adapter || '').trim().toLowerCase() === String(value.platform || value.adapter || '').trim().toLowerCase() && String(row.bot_id || '') === String(value.bot_id || '');
  const adapterName = (name, id) => String(name || '').trim() && String(name).trim() !== String(id) ? String(name).trim() : '';
  const candidates = (() => {
    const byIdentity = new Map();
    const addCandidate = (candidate) => {
      const id = String(candidate.id || '').trim(); if (!id) return;
      const key = `${candidate.kind || 'private'}:${id}`; const previous = byIdentity.get(key);
      const name = adapterName(candidate.name, id);
      byIdentity.set(key, { ...previous, ...candidate, id, name: name || previous?.name || '' });
    };
    if (draft.list === 'admins' || draft.kind === 'private') {
      users.forEach((user) => addCandidate({ ...user, kind: 'private' }));
      conversations.filter((row) => sameAccount(row) && row.kind === 'private').forEach((row) => {
        addCandidate({ id: row.user_id || row.peer_id, name: adapterName(row.name, row.user_id || row.peer_id), kind: 'private' });
      });
    }
    if (draft.list !== 'admins' && draft.kind === 'group') {
      groups.filter(sameAccount).forEach((row) => addCandidate({ id: row.group_id, name: adapterName(row.name, row.group_id), kind: 'group' }));
      conversations.filter((row) => sameAccount(row) && row.kind === 'group').forEach((row) => addCandidate({ id: row.peer_id, name: adapterName(row.name, row.peer_id), kind: 'group' }));
    }
    return [...byIdentity.values()].sort((a, b) => (a.name || a.id).localeCompare(b.name || b.id, 'zh-CN'));
  })();
  const normalizedList = (list, defaultKind) => (Array.isArray(value[list]) ? value[list] : []).map((item) => {
    if (item && typeof item === 'object') return { ...item, id: String(item.id || ''), kind: item.kind || defaultKind };
    return { id: String(item || ''), name: '', kind: defaultKind };
  }).filter((item) => item.id);
  const adapterDisplayName = (row) => {
    const id = String(row.id); const kind = row.kind || 'private';
    if (kind === 'group') {
      const group = groups.find((item) => sameAccount(item) && String(item.group_id) === id);
      const conversation = conversations.find((item) => sameAccount(item) && item.kind === 'group' && String(item.peer_id) === id);
      return adapterName(group?.name, id) || adapterName(conversation?.name, id);
    }
    return adapterName(users.find((item) => item.id === id)?.name, id)
      || adapterName(conversations.find((item) => sameAccount(item) && item.kind === 'private' && (String(item.user_id) === id || String(item.peer_id) === id))?.name, id);
  };
  const displayName = (row) => adapterDisplayName(row) || adapterName(row.name, row.id) || String(row.id);
  const append = (list, row) => {
    const defaultKind = list === 'admins' ? 'private' : draft.kind;
    const existing = normalizedList(list, defaultKind);
    if (!existing.some((item) => item.id === String(row.id) && (list === 'admins' || item.kind === row.kind))) onChange({ [list]: [...existing, { ...row, id: String(row.id) }] });
  };
  function add() {
    const id = draft.id.trim(); if (!id) return;
    const kind = draft.list === 'admins' ? 'private' : draft.kind;
    const candidate = candidates.find((item) => item.id === id && item.kind === kind);
    append(draft.list, { id, name: draft.name.trim() || candidate?.name || '', kind });
    setDraft({ ...draft, id: '', name: '' });
  }
  function remove(list, row) { const defaultKind = list === 'admins' ? 'private' : row.kind || 'private'; onChange({ [list]: normalizedList(list, defaultKind).filter((item) => item.id !== String(row.id) || (list !== 'admins' && item.kind !== (row.kind || 'private'))) }); }
  const adminIds = new Set(normalizedList('admins', 'private').map((item) => item.id));
  return <section className="access-editor"><div className="section-title"><h3>访问名单</h3><span className="muted">显示名称优先采用 adapter 昵称，ID 用于精确匹配；管理员和名单修改后点击“保存设置”生效</span></div><div className="form-grid two"><SelectField label="名单" value={draft.list} options={['admins', 'whitelist', 'blacklist']} labels={['管理员', '白名单', '黑名单']} onChange={(list) => setDraft({ ...draft, list, id: '', name: '' })} /><SelectField label="会话类型" value={draft.list === 'admins' ? 'private' : draft.kind} options={['private', 'group']} labels={['私聊用户', '群聊']} onChange={(kind) => setDraft({ ...draft, kind, id: '', name: '' })} /><SelectField label={draft.kind === 'group' && draft.list !== 'admins' ? '选择已发现群聊' : '选择已发现私聊'} value={draft.id} options={['', ...candidates.map((row) => row.id)]} labels={[candidates.length ? '选择名称或 ID' : '暂无可选对象，可手动输入 ID', ...candidates.map((row) => `${row.name || row.id} · ${row.id}`)]} onChange={(id) => { const candidate = candidates.find((row) => row.id === id); setDraft({ ...draft, id, name: candidate?.name || '' }); }} /><Field label="用户 / 群 ID" value={draft.id} onChange={(id) => setDraft({ ...draft, id, name: candidates.find((row) => row.id === id)?.name || '' })} /><Field label="显示名称（可选）" value={draft.name} onChange={(name) => setDraft({ ...draft, name })} /></div><button className="soft-button access-add" onClick={add} disabled={!draft.id.trim()}><Plus size={14} />加入名单</button><Field label="筛选名单" value={filter} onChange={setFilter} placeholder="搜索 ID 或名称" />{[['admins', '管理员'], ['whitelist', '白名单'], ['blacklist', '黑名单']].map(([list, label]) => { const rows = normalizedList(list, 'private').filter((row) => `${row.id} ${displayName(row)}`.toLowerCase().includes(filter.toLowerCase())); return <div className="access-list" key={list}><strong>{label}（{rows.length}）</strong>{rows.map((row) => <div className="access-row" key={`${row.kind}-${row.id}`}><span>{row.kind === 'group' ? '群聊' : '私聊'} · {displayName(row)}<small>{row.id}</small></span><button className="icon-button danger" title="移出名单" onClick={() => remove(list, row)}><Trash2 size={14} /></button></div>)}</div>; })}<div className="access-list"><strong>最近私聊用户（{users.length}）</strong>{users.filter((row) => `${row.id} ${row.name || ''}`.toLowerCase().includes(filter.toLowerCase())).map((row) => <div className="access-row" key={row.id}><span>{adapterDisplayName({ ...row, kind: 'private' }) || adapterName(row.name, row.id) || row.id}<small>{row.id}</small></span><button className="soft-button" onClick={() => append('admins', { id: row.id, name: adapterDisplayName({ ...row, kind: 'private' }) || row.name, kind: 'private' })} disabled={adminIds.has(row.id)}>{adminIds.has(row.id) ? '已是管理员' : '设为管理员'}</button></div>)}{users.length === 0 && <Empty title="还没有私聊用户" detail="收到一条私聊消息后，可从这里直接设为管理员。" />}</div></section>;
}

function Personas({ token, roles, onRolesChange }) {
  const [editor, setEditor] = useState(null);
  async function reload() { onRolesChange(await api(token, '/roles')); }
  async function save() { if (!editor?.name?.trim()) return; await api(token, editor.original ? `/roles/${encodeURIComponent(editor.original)}` : '/roles', editor.original ? 'PUT' : 'POST', editor.original ? { value: editor.content } : { name: editor.name.trim(), content: editor.content }); await reload(); setEditor(null); }
  async function activate(name) { await api(token, '/active-role', 'PUT', { name: name || null }); await reload(); }
  async function remove(name) { if (!window.confirm(`确认删除人格模板“${name}”？`)) return; await api(token, `/roles/${encodeURIComponent(name)}`, 'DELETE'); await reload(); }
  async function copy(name) { const next = window.prompt('新模板名称', `${name}-副本`); if (next) { await api(token, `/roles/${encodeURIComponent(name)}/copy`, 'POST', { name: next }); await reload(); } }
  return <div className="page-stack"><PageIntro kicker="PERSONA WORKBENCH" title="人格提示" detail="创建可复用的人格模板，并在平台账号中选择模板，再追加账号专属提示。" action="新建模板" onClick={() => setEditor({ name: '', content: '' })} /><section className="surface table-surface"><div className="table-toolbar"><div className="toolbar-label"><Sparkles size={17} /><span>{roles.roles.length} 个模板</span></div><span className="muted">当前默认：{roles.active || '未设置'}</span></div><div className="data-table">{roles.roles.length ? roles.roles.map((role) => <div className="data-row" key={role.name}><div className="identity-cell"><span className="capability-icon"><Sparkles size={16} /></span><div><strong>{role.name}</strong><small>{role.chars} 字 · {role.sections?.length || 0} 个章节</small></div></div><div><span className="cell-label">状态</span><span>{roles.active === role.name ? '全局默认' : '可选模板'}</span></div><div className="row-actions"><button className="soft-button" onClick={() => activate(roles.active === role.name ? null : role.name)}>{roles.active === role.name ? '取消默认' : '设为默认'}</button><button className="icon-button" title="复制" onClick={() => copy(role.name)}><Plus size={15} /></button><button className="icon-button" title="编辑" onClick={() => setEditor({ name: role.name, original: role.name, content: role.content })}><Pencil size={15} /></button><button className="icon-button danger" title="删除" onClick={() => remove(role.name)}><Trash2 size={15} /></button></div></div>) : <Empty title="还没有人格模板" detail="创建第一个模板后，就能在平台账号中直接选择。" />}</div></section>{editor && <Modal title={editor.original ? '编辑人格模板' : '新建人格模板'} onClose={() => setEditor(null)}><div className="form-grid"><Field label="模板名称" value={editor.name} onChange={(name) => setEditor({ ...editor, name })} /><Field label={`人格内容（${(editor.content || '').length} / 24000）`} wide type="textarea" value={editor.content} onChange={(content) => setEditor({ ...editor, content })} placeholder="写下说话风格、边界和角色规则" /></div><ModalFooter onClose={() => setEditor(null)} onSave={save} /></Modal>}</div>;
}

function Groups({ token, snapshot, tools, onRefresh }) {
  const [editor, setEditor] = useState(null); const groups = snapshot.groups || []; const accounts = snapshot.accounts || []; const providers = snapshot.interfaces?.providers || [];
  async function save(body) { await api(token, editor.id ? `/groups/${editor.id}` : '/groups', editor.id ? 'PUT' : 'POST', body); await onRefresh(); setEditor(null); }
  async function remove(id) { if (!window.confirm('确认删除这个群聊策略？')) return; await api(token, `/groups/${id}`, 'DELETE'); await onRefresh(); }
  return <div className="page-stack"><PageIntro kicker="GROUP POLICIES" title="群聊策略" detail="群聊提示词会完整覆盖账号人格；回复概率 0~1，未命中的消息会暂存并在下次回复时一并带上时间戳交给模型。" action="添加策略" onClick={() => setEditor({})} /><section className="surface table-surface"><div className="table-toolbar"><div className="toolbar-label"><UsersRound size={17} /><span>{groups.length} 个群聊策略</span></div><span className="muted">群名称优先来自 adapter</span></div><div className="data-table">{groups.length ? groups.map((group) => { const provider = providers.find((p) => p.id === group.provider_id); return <div className="data-row" key={group.id}><div className="identity-cell"><span className="group-avatar"><MessageSquareText size={17} /></span><div><strong>{group.name || group.group_id}</strong><small>{group.platform} / {group.bot_id} · {group.group_id}</small></div></div><div><span className="cell-label">供应商</span><span>{providerLabel(provider) || '跟随账号'}</span></div><div><span className="cell-label">模型</span><span>{modelId(group.model) || modelId(provider?.model) || '账号默认'}</span></div><div><span className="cell-label">工具</span><span>{group.enabled_tools?.length || '继承默认'}</span></div><div><span className="cell-label">回复概率</span><span>{group.reply_probability ?? 1}</span></div><Status enabled={group.enabled !== false} /><div className="row-actions"><button className="icon-button" title="编辑策略" onClick={() => setEditor(group)}><Pencil size={15} /></button><button className="icon-button danger" title="删除策略" onClick={() => remove(group.id)}><Trash2 size={15} /></button></div></div>; }) : <Empty title="还没有群聊策略" detail="先添加账号，再为账号绑定群聊 ID。" />}</div></section>{editor && <GroupEditor value={editor} accounts={accounts} providers={providers} tools={tools} onClose={() => setEditor(null)} onSave={save} />}</div>;
}

function GroupEditor({ value, accounts, providers, tools, onClose, onSave }) {
  const first = accounts.find((a) => a.platform === value.platform && a.bot_id === value.bot_id); const [form, setForm] = useState({ enabled: true, reply_probability: 1, reasoning_effort: 'medium', enabled_tools: null, ...value, account_id: first?.id || '' }); const set = (key, next) => setForm((p) => ({ ...p, [key]: next })); const account = accounts.find((a) => a.id === form.account_id); const provider = providers.find((p) => p.id === form.provider_id); const models = provider?.models || [];
  return <Modal title={value.id ? '编辑群聊策略' : '添加群聊策略'} onClose={onClose}><div className="form-grid two"><SelectField label="绑定账号" value={form.account_id} options={['', ...accounts.map((a) => a.id)]} labels={['选择账号', ...accounts.map((a) => `${a.name || a.bot_id} · ${a.platform}`)]} onChange={(v) => { const next = accounts.find((a) => a.id === v); setForm({ ...form, account_id: v, platform: next?.platform || '', bot_id: next?.bot_id || '' }); }} /><Field label="群 ID" value={form.group_id || ''} onChange={(v) => set('group_id', v)} /><Field label="群名称" value={form.name || ''} onChange={(v) => set('name', v)} placeholder="留空则使用群 ID" /><SelectField label="AI 供应商" value={form.provider_id || ''} options={['', ...providers.map((p) => p.id)]} labels={['跟随账号', ...providers.map(providerLabel)]} onChange={(v) => set('provider_id', v)} /><SelectField label="模型" value={modelId(form.model)} options={['', ...models.map((m) => m.id)]} labels={['供应商默认', ...models.map((m) => `${m.id}${m.context_length ? ` · ${m.context_length.toLocaleString()} tokens` : ''}`)]} onChange={(v) => set('model', v)} /><Field label="回复概率（0 永不回复 · 1 一直回复）" type="number" min="0" max="1" step="0.05" value={form.reply_probability ?? 1} onChange={(v) => set('reply_probability', v)} /><SelectField label="思考强度" value={form.reasoning_effort || 'medium'} options={['low', 'medium', 'high']} labels={['低', '中', '高']} onChange={(v) => set('reasoning_effort', v)} /><Field label="成本上限" type="number" value={form.cost_limit ?? ''} onChange={(v) => set('cost_limit', v)} /><Field label="群聊提示词（完整覆盖账号人格）" wide type="textarea" value={form.system_prompt || ''} onChange={(v) => set('system_prompt', v)} placeholder="留空则继承账号人格模板和补充提示" /></div><ToolSelection value={form.enabled_tools} tools={tools} onChange={(v) => set('enabled_tools', v)} /><ModalFooter onClose={onClose} onSave={() => onSave({ ...form, platform: account?.platform || form.platform || '', bot_id: account?.bot_id || form.bot_id || '', enabled: form.enabled !== false, reply_probability: form.reply_probability ?? 1, cost_limit: form.cost_limit === '' ? null : Number(form.cost_limit) || null })} /></Modal>;
}

function ToolSelection({ value, tools, onChange }) {
  const inherited = value == null; const selected = value || []; function toggle(name) { onChange(selected.includes(name) ? selected.filter((x) => x !== name) : [...selected, name]); }
  return <div className="tool-pickers"><div className="tool-picker wide-tool-picker"><div className="tool-picker-head"><strong><Wrench size={15} />工具默认</strong><label className="check-row"><input type="checkbox" checked={inherited} onChange={(e) => onChange(e.target.checked ? null : tools.map((t) => t.name))} />继承可用工具</label></div>{!inherited && <div className="tool-check-grid">{tools.map((tool) => <label key={tool.name} className="check-row" title={tool.description}><input type="checkbox" checked={selected.includes(tool.name)} onChange={() => toggle(tool.name)} /><span>{tool.name}</span></label>)}</div>}</div></div>;
}

function Interfaces({ token, snapshot, tools, onRefresh }) {
  const [tab, setTab] = useState('providers'); const [editor, setEditor] = useState(null); const rows = tab === 'tools' ? tools : snapshot.interfaces?.[tab] || [];
  async function save(body) { await api(token, editor.id ? `/interfaces/${tab}/${editor.id}` : `/interfaces/${tab}`, editor.id ? 'PUT' : 'POST', body); await onRefresh(); setEditor(null); }
  async function remove(id) { if (!window.confirm('确认删除这个能力？')) return; await api(token, `/interfaces/${tab}/${id}`, 'DELETE'); await onRefresh(); }
  async function discover(id) { await api(token, `/interfaces/providers/${id}/models`, 'POST'); await onRefresh(); }
  const tabs = [['providers', 'AI 接口'], ['tools', 'Tools'], ['skills', 'Skill'], ['mcps', 'MCP'], ['rules', 'Rules']];
  return <div className="page-stack"><PageIntro kicker="INTERFACE CAPABILITIES" title="接口能力" detail="管理 AI 接口、实际可用 Tools，以及群聊策略可以勾选的能力目录。" action={tab === 'tools' ? null : '新增能力'} onClick={() => setEditor({})} /><section className="surface"><div className="tabs">{tabs.map(([id, label]) => <button key={id} className={tab === id ? 'active' : ''} onClick={() => setTab(id)}>{label}</button>)}</div>{tab === 'mcps' && <OpenWebSearchCard token={token} />}<div className="data-table">{rows.length ? rows.map((row) => <div className="data-row" key={row.id || row.name}><div className="identity-cell"><span className="capability-icon">{tab === 'tools' ? <Wrench size={16} /> : <Plug size={16} />}</span><div><strong>{row.name || row.id}</strong><small>{row.description || row.base_url || row.url || row.content || row.category || '尚未填写描述'}</small></div></div><div><span className="cell-label">{tab === 'providers' ? '模型' : tab === 'tools' ? '来源' : '类型'}</span><span>{tab === 'providers' ? `${row.models?.length || 0} 个已发现` : tab === 'tools' ? row.source : tab.toUpperCase()}</span></div><div className="row-actions">{tab === 'providers' && <button className="soft-button" onClick={() => discover(row.id)}><RefreshCw size={14} />拉取模型</button>}{tab !== 'tools' && <><button className="icon-button" title="编辑" onClick={() => setEditor(row)}><Pencil size={15} /></button><button className="icon-button danger" title="删除" onClick={() => remove(row.id)}><Trash2 size={15} /></button></>}</div></div>) : <Empty title={tab === 'tools' ? '暂无可用工具' : '还没有接口能力'} detail={tab === 'tools' ? '工具会根据当前桥接模式和 MCP 连接显示。' : '新增 AI 接口后可以在窗口中拉取模型。'} />}</div></section>{editor && <CapabilityEditor token={token} kind={tab} value={editor} onClose={() => setEditor(null)} onSave={save} />}</div>;
}

function CapabilityEditor({ token, kind, value, onClose, onSave }) {
  const [form, setForm] = useState({ ...value }); const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const set = (key, next) => setForm((p) => ({ ...p, [key]: next }));
  async function discover() { setBusy(true); setError(''); try { const result = await api(token, '/interfaces/providers/discover', 'POST', { base_url: form.base_url || '', api_key: form.api_key || '' }); setForm((p) => ({ ...p, models: result.models })); } catch (err) { setError(err.message); } finally { setBusy(false); } }
  if (kind === 'providers') { const models = form.models || []; const selected = models.find((m) => m.id === modelId(form.model)); return <Modal title={value.id ? '编辑 AI 接口' : '新增 AI 接口'} onClose={onClose}><div className="form-grid two"><Field label="接口名称" value={form.name || ''} onChange={(v) => set('name', v)} /><Field label="Base URL" value={form.base_url || ''} onChange={(v) => set('base_url', v)} placeholder="https://api.example.com/v1" /><Field label="API Key" type="password" value={form.api_key || ''} onChange={(v) => set('api_key', v)} /><Field label="备用上下文大小" type="number" value={form.context_length || ''} onChange={(v) => set('context_length', v)} placeholder="远端未提供时使用" /><div className="field wide"><span>远端模型</span><div className="inline-actions"><button className="soft-button" disabled={busy} onClick={discover}><RefreshCw size={14} className={busy ? 'spin' : ''} />{busy ? '获取中…' : '获取模型'}</button><span className="muted">已获取 {models.length} 个模型</span></div></div><SelectField label="默认模型" value={modelId(form.model)} options={['', ...models.map((m) => m.id)]} labels={['不设置', ...models.map((m) => `${m.id}${m.context_length ? ` · ${m.context_length.toLocaleString()} tokens` : ''}`)]} onChange={(v) => set('model', v)} /><div className="field wide"><span>上下文说明</span><span className="muted">{selected?.context_length ? `当前模型远端上下文：${selected.context_length.toLocaleString()} tokens` : '当前模型未返回上下文，将使用备用设置或全局设置。'}</span></div></div>{error && <div className="form-error"><CircleAlert size={15} />{error}</div>}<ModalFooter onClose={onClose} onSave={() => onSave({ ...form, context_length: Number(form.context_length) || null })} /></Modal>; }
  const labels = { skills: ['Skill 名称', '描述'], mcps: ['MCP 名称', '服务地址'], rules: ['Rule 名称', '规则内容'] }[kind]; const contentKey = kind === 'mcps' ? 'url' : kind === 'rules' ? 'content' : 'description';
  return <Modal title={value.id ? '编辑能力' : '新增能力'} onClose={onClose}><div className="form-grid"><Field label={labels[0]} value={form.name || ''} onChange={(v) => set('name', v)} /><Field label={labels[1]} wide type="textarea" value={form[contentKey] || ''} onChange={(v) => set(contentKey, v)} /></div><ModalFooter onClose={onClose} onSave={() => onSave(form)} /></Modal>;
}

function OpenWebSearchCard({ token }) {
  const [status, setStatus] = useState({ url: '', connected: false, error: '', tools: [] });
  const [draft, setDraft] = useState(''); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  useEffect(() => { api(token, '/mcp').then((next) => { setStatus(next); setDraft(next.url || ''); }).catch((err) => setError(err.message)); }, [token]);
  async function connect(value) {
    setBusy(true); setError('');
    try { const next = await api(token, '/mcp', 'PUT', { value }); setStatus(next); setDraft(next.url || ''); }
    catch (err) { setError(err.message); } finally { setBusy(false); }
  }
  const enabled = !!status.url;
  return <div className="mcp-card">
    <div className="mcp-card-head"><div><span className="kicker">BUILT-IN MCP</span><strong>open_websearch</strong><small>内置搜索 MCP；清空服务地址即禁用。工具在会话的工具配置中单独启用。</small></div><Status enabled={status.connected} /></div>
    <label className="check-row"><input type="checkbox" checked={enabled} onChange={(event) => { if (!event.target.checked) connect(''); else { const next = draft || status.url || 'http://localhost:3000/mcp'; setDraft(next); connect(next); } }} />启用内置 MCP</label>
    <div className="mcp-card-actions"><input aria-label="MCP 服务地址" value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="http://localhost:3000/mcp" /><button className="soft-button" disabled={busy} onClick={() => connect(draft.trim())}><RefreshCw size={14} className={busy ? 'spin' : ''} />{busy ? '连接中…' : '连接 / 重新发现'}</button></div>
    {(error || status.error) && <div className="form-error"><CircleAlert size={15} />{error || status.error}</div>}
    <div className="inline-actions"><span className="muted">已发现 {status.tools?.length || 0} 个工具</span>{(status.tools || []).map((tool) => <span className="soft-tag" key={tool.name}>{tool.name}</span>)}</div>
  </div>;
}

function conversationLabel(row) {
  const scope = row.kind === 'group' ? '群聊' : '私聊';
  return `${scope} · ${row.name || row.peer_id || '未知会话'}`;
}

function messageText(content) {
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) return content.map((item) => item?.text || item?.content || `[${item?.type || '内容'}]`).join('');
  return content ? JSON.stringify(content) : '';
}

function Logs({ token, snapshot }) {
  const [logs, setLogs] = useState({ activity: snapshot.activity || [], usage: snapshot.usage || [], conversations: snapshot.conversations || [] });
  const [scope, setScope] = useState('all'); const [status, setStatus] = useState('all'); const [query, setQuery] = useState(''); const [selectedKey, setSelectedKey] = useState(''); const [detail, setDetail] = useState(null); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  async function reload() { const next = await api(token, '/logs'); setLogs(next); setError(''); return next; }
  useEffect(() => { reload().catch((err) => setError(err.message)); }, [token]);
  const conversations = logs.conversations.filter((row) => (scope === 'all' || row.kind === scope) && (status === 'all' || (row.status || 'approved') === status) && `${row.name || ''} ${row.peer_id} ${row.platform} ${row.bot_id}`.toLowerCase().includes(query.toLowerCase()));
  useEffect(() => { if (!conversations.some((row) => row.key === selectedKey)) setSelectedKey(conversations[0]?.key || ''); }, [scope, status, query, logs.conversations]);
  useEffect(() => {
    let active = true;
    setDetail(null);
    if (selectedKey) api(token, `/conversations/${selectedKey}`).then((next) => { if (active) setDetail(next); }).catch((err) => { if (active) setError(err.message); });
    return () => { active = false; };
  }, [token, selectedKey]);
  async function reviewConversation(nextStatus) {
    if (!selectedKey || detail?.key !== selectedKey) return;
    setBusy(true); setError('');
    try { await api(token, `/conversations/${selectedKey}/status`, 'PUT', { status: nextStatus }); await reload(); setDetail(await api(token, `/conversations/${selectedKey}`)); }
    catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  async function clearConversation() {
    if (!selectedKey || detail?.key !== selectedKey || !window.confirm('确认清空这个会话的全部聊天记录？')) return;
    setBusy(true); setError('');
    try { await api(token, `/conversations/${selectedKey}/reset`, 'POST'); setDetail(await api(token, `/conversations/${selectedKey}`)); await reload(); }
    catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  return <div className="page-stack"><PageIntro kicker="CONVERSATION LOG" title="对话日志" detail={error || '筛选会话状态，确认新会话并查看 Agent 记录。'} /><section className="surface conversation-surface"><div className="conversation-toolbar"><div className="tabs compact-tabs"><button className={scope === 'all' ? 'active' : ''} onClick={() => setScope('all')}>全部</button><button className={scope === 'group' ? 'active' : ''} onClick={() => setScope('group')}><UsersRound size={14} />群聊</button><button className={scope === 'private' ? 'active' : ''} onClick={() => setScope('private')}><MessageCircle size={14} />私聊</button></div><select aria-label="会话状态" value={status} onChange={(event) => setStatus(event.target.value)}><option value="all">全部状态</option><option value="pending">待确认</option><option value="approved">已确认</option><option value="rejected">已拒绝</option></select><input aria-label="搜索会话" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索名称、ID 或平台" /><button className="soft-button" onClick={() => reload().catch((err) => setError(err.message))} disabled={busy}><RefreshCw size={14} />刷新记录</button><span className="muted">{conversations.length} 个会话</span></div><div className="conversation-browser"><aside className="conversation-list">{conversations.length ? conversations.map((row) => <button key={row.key} className={`conversation-item ${selectedKey === row.key ? 'active' : ''}`} onClick={() => setSelectedKey(row.key)}><span className="conversation-icon">{row.kind === 'group' ? <UsersRound size={15} /> : <MessageCircle size={15} />}</span><span><strong>{conversationLabel(row)}</strong><small>{row.platform} · {row.bot_id} · {row.peer_id}</small><small>{row.status === "pending" ? "待确认" : row.status === "rejected" ? "已拒绝" : "已确认"}</small></span></button>) : <Empty title="暂无会话" detail="收到群聊或私聊消息后，会话会显示在这里。" />}</aside><div className="transcript-panel">{detail ? <><div className="transcript-head"><div><strong>{conversationLabel(detail)}</strong><small>{detail.platform} · {detail.bot_id} · {detail.peer_id} · {detail.status === "pending" ? "待确认" : detail.status === "rejected" ? "已拒绝" : "已确认"}</small></div><div className="inline-actions">{detail.status !== "approved" && <button className="soft-button" onClick={() => reviewConversation("approved")} disabled={busy}><Check size={14} />确认会话</button>}{detail.status !== "rejected" && <button className="soft-button danger-button" onClick={() => reviewConversation("rejected")} disabled={busy}>拒绝</button>}<button className="soft-button danger-button" onClick={clearConversation} disabled={busy}><Trash2 size={14} />{busy ? '处理中…' : '清空聊天记录'}</button></div></div><div className="transcript">{detail.messages?.length ? detail.messages.map((message, index) => <div className={`message-bubble ${message.role}`} key={`${message.role}-${index}`}><span className="message-role">{message.role === 'user' ? '用户' : message.role === 'assistant' ? 'Agent' : message.role === 'tool' ? '工具' : message.role}</span><div>{messageText(message.content) || (message.tool_calls?.length ? `调用工具：${message.tool_calls.map((call) => call.name).join('、')}` : '（空消息）')}</div></div>) : <Empty title="这个会话还没有消息" detail="新消息会自动出现在这里。" />}</div></> : <Empty title="选择一个会话" detail="从左侧选择群聊或私聊，查看对应的 Agent 记录。" />}</div></div></section><div className="logs-grid"><section className="surface"><SectionTitle title="活动流" /><div className="log-list">{logs.activity.length ? logs.activity.slice().reverse().map((item, index) => <div className="log-row" key={`${item.at}-${index}`}><span className="log-time">{formatTime(item.at)}</span><span>{item.text}</span></div>) : <Empty title="暂无活动记录" detail="收到消息后会显示事件摘要。" />}</div></section><section className="surface"><SectionTitle title="用量记录" /><div className="usage-list">{logs.usage.length ? logs.usage.slice().reverse().slice(0, 12).map((item, index) => <div className="usage-row" key={`${item.at}-${index}`}><div><strong>{item.conversation?.slice(0, 10) || 'session'}</strong><small>{formatTime(item.at)}</small></div><span>{item.total || 0} tokens</span><b>${Number(item.estimated_cost || 0).toFixed(4)}</b></div>) : <Empty title="暂无用量记录" detail="模型调用后会显示 token 与估算成本。" />}</div></section></div></div>;
}

function Memory({ token, snapshot, onRefresh }) {
  const accounts = snapshot?.accounts || [];
  const [tab, setTab] = useState('global'); const [accountId, setAccountId] = useState(accounts[0]?.id || '');
  const [memories, setMemories] = useState([]); const [index, setIndex] = useState(''); const [queue, setQueue] = useState([]);
  const [slang, setSlang] = useState([]); const [settings, setSettings] = useState({ enabled: true, min_messages: 10, cooldown_seconds: 300, review_provider_id: '', review_model: '', review_configured: false });
  const [editor, setEditor] = useState(null); const [error, setError] = useState('');
  const [botSettings, setBotSettings] = useState({ enabled: true, interval: 50 }); const [savingSettings, setSavingSettings] = useState(false);
  const [reviewDraft, setReviewDraft] = useState({ review_provider_id: '', review_model: '' });
  const account = accounts.find((row) => row.id === accountId);
  const memoryBase = tab === 'bot' && account ? `/accounts/${account.id}/memories` : '/memories';
  const slug = (title) => title.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 64) || `memory-${Date.now()}`;
  async function reload() {
    const [memoryRows, memoryIndex, queueRows, slangRows, slangSettings] = await Promise.all([
      tab === 'bot' && account ? api(token, memoryBase) : api(token, '/memories'),
      tab === 'global' ? api(token, '/memories/index') : Promise.resolve({ content: '' }),
      api(token, '/memory-queue'), api(token, '/slang'), api(token, '/slang/settings'),
    ]);
    setMemories(memoryRows); setIndex(memoryIndex.content || ''); setQueue(queueRows); setSlang(slangRows); setSettings(slangSettings); setError('');
  }
  useEffect(() => { if (!accountId && accounts[0]) setAccountId(accounts[0].id); }, [accounts, accountId]);
  useEffect(() => { setBotSettings({ enabled: account?.memory_enabled !== false, interval: account?.memory_interval || 50 }); }, [accountId, account?.memory_enabled, account?.memory_interval]);
  useEffect(() => { reload().catch((err) => setError(err.message)); }, [token, tab, accountId]);
  useEffect(() => { setReviewDraft({ review_provider_id: settings.review_provider_id || '', review_model: settings.review_model || '' }); }, [settings.review_provider_id, settings.review_model]);
  async function saveBotSettings() {
    if (!account) return;
    setSavingSettings(true);
    try { await api(token, `/accounts/${account.id}`, 'PUT', { memory_enabled: botSettings.enabled, memory_interval: Number(botSettings.interval) || 50 }); await onRefresh(); setError(''); }
    catch (err) { setError(err.message); }
    finally { setSavingSettings(false); }
  }
  function newMemory() { setEditor({ name: '', title: '', description: '', type: 'project', content: '' }); }
  async function saveMemory() {
    try {
      const body = { name: editor.name.trim() || slug(editor.title), title: editor.title.trim(), description: editor.description.trim(), type: editor.type || 'project', content: editor.content.trim() };
      if (editor.queueId) await api(token, `/memory-queue/${editor.queueId}`, 'PATCH', body);
      else await api(token, editor.original ? `${memoryBase}/${encodeURIComponent(editor.original)}` : memoryBase, editor.original ? 'PUT' : 'POST', body);
      await reload(); setEditor(null);
    } catch (err) { setError(err.message); }
  }
  async function openMemory(row) {
    try { setEditor({ ...(await api(token, `${memoryBase}/${encodeURIComponent(row.name)}`)), original: row.name }); }
    catch (err) { setError(err.message); }
  }
  async function removeMemory(name) {
    if (!window.confirm(`确认删除记忆“${name}”？`)) return;
    try { await api(token, `${memoryBase}/${encodeURIComponent(name)}`, 'DELETE'); await reload(); }
    catch (err) { setError(err.message); }
  }
  async function approveCandidate(row) {
    const name = row.name || slug(row.title);
    try { await api(token, `/memory-queue/${row.id}/approve`, 'POST', { name }); await reload(); }
    catch (err) { setError(err.message); }
  }
  async function removeCandidate(id) {
    if (!window.confirm('删除这条待审核记忆？')) return;
    try { await api(token, `/memory-queue/${id}`, 'DELETE'); await reload(); }
    catch (err) { setError(err.message); }
  }
  async function saveSlang() {
    try { const body = { term: editor.term.trim(), meaning: editor.meaning || '' }; if (editor.id) await api(token, `/slang/${editor.id}`, 'PATCH', { ...body, status: editor.status }); else await api(token, '/slang', 'POST', body); await reload(); setEditor(null); }
    catch (err) { setError(err.message); }
  }
  async function updateSettings(next) { try { const saved = await api(token, '/slang/settings', 'PUT', next); setSettings(saved); setError(''); } catch (err) { setError(err.message); } }
  async function saveReviewSettings() { await updateSettings({ ...settings, ...reviewDraft }); }
  async function reviewSlang(row) { try { await api(token, `/slang/${row.id}`, 'PATCH', { status: row.status === 'confirmed' ? 'candidate' : 'confirmed' }); await reload(); } catch (err) { setError(err.message); } }
  async function removeSlang(id) { if (!window.confirm('确认删除这个黑话词条？')) return; try { await api(token, `/slang/${id}`, 'DELETE'); await reload(); } catch (err) { setError(err.message); } }
  const memoryTabs = [['global', '全局 Memory'], ['bot', 'Bot Memory'], ['review', `待审核（${queue.length}）`], ['slang', '黑话词库']];
  const showMemoryEditor = editor && ['global', 'bot'].includes(tab);
  return <div className="page-stack">
    <PageIntro kicker="MEMORY WORKBENCH" title="记忆管理" detail={error || '管理全局与 Bot 专属 Memory，并审核自动整理的记忆草稿。'} action={tab === 'global' || (tab === 'bot' && account) ? '新增记忆' : tab === 'slang' ? '新增黑话' : ''} onClick={tab === 'slang' ? () => setEditor({ term: '', meaning: '', status: 'candidate' }) : newMemory} />
    <section className="surface"><div className="tabs">{memoryTabs.map(([key, label]) => <button key={key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>{key === 'slang' ? <MessageSquareText size={14} /> : key === 'review' ? <Check size={14} /> : <BookOpen size={14} />}{label}</button>)}</div>
      {['global', 'bot'].includes(tab) && <>
        {tab === 'bot' && <div className="slang-settings"><label className="field"><span>Bot 账号</span><select value={accountId} onChange={(event) => setAccountId(event.target.value)}>{accounts.map((row) => <option key={row.id} value={row.id}>{row.name || row.bot_id} · {row.platform} / {row.bot_id}</option>)}</select></label>{account && <><label className="check-row"><input type="checkbox" checked={botSettings.enabled} onChange={(event) => setBotSettings({ ...botSettings, enabled: event.target.checked })} />自动整理待审核记忆</label><label className="field"><span>收到消息数量</span><input type="number" min="1" max="1000" value={botSettings.interval} onChange={(event) => setBotSettings({ ...botSettings, interval: event.target.value })} /></label><button className="soft-button" onClick={saveBotSettings} disabled={savingSettings}>{savingSettings ? '保存中…' : '保存 Bot 设置'}</button></>}</div>}
        {tab === 'bot' && !account && <Empty title="还没有 Bot 账号" detail="添加平台账号后，可为每个 Bot 单独维护 Memory。" />}
        {(tab === 'global' || account) && <div className="memory-layout"><div className="data-table">{memories.length ? memories.map((row) => <div className="data-row memory-row" key={row.name}><div className="identity-cell"><span className="capability-icon"><BookOpen size={16} /></span><div><strong>{row.title}</strong><small>{row.name} · {row.type} · {row.chars} 字</small></div></div><div><span className="cell-label">说明</span><span>{row.description}</span></div><div className="row-actions"><button className="icon-button" title="编辑" onClick={() => openMemory(row)}><Pencil size={15} /></button><button className="icon-button danger" title="删除" onClick={() => removeMemory(row.name)}><Trash2 size={15} /></button></div></div>) : <Empty title={tab === 'global' ? '还没有全局记忆' : '这个 Bot 还没有记忆'} detail="添加长期有效的信息；自动总结的内容需先在待审核列表中通过。" />}</div>{tab === 'global' && <div className="memory-index"><SectionTitle title="Memory.md 索引" /><pre>{index || '索引为空，新增记忆后会自动生成。'}</pre></div>}</div>}
      </>}
      {tab === 'review' && <div className="data-table">{queue.length ? queue.map((row) => <div className="data-row memory-row" key={row.id}><div className="identity-cell"><span className="capability-icon"><BookOpen size={16} /></span><div><strong>{row.title}</strong><small>{row.platform} / {row.bot_id} · {row.source_messages} 条消息 · {formatTime(row.created_at)}</small></div></div><div><span className="cell-label">摘要</span><span>{row.description}<br />{row.content}</span></div><div className="row-actions"><button className="soft-button" onClick={() => approveCandidate(row)}>通过</button><button className="icon-button" title="编辑" onClick={() => setEditor({ ...row, queueId: row.id, name: row.name || slug(row.title) })}><Pencil size={15} /></button><button className="icon-button danger" title="删除" onClick={() => removeCandidate(row.id)}><Trash2 size={15} /></button></div></div>) : <Empty title="没有待审核记忆" detail="Bot 按账号设置的消息数量整理出草稿后，会显示在这里。" />}</div>}
      {tab === 'slang' && <><div className="slang-settings"><label className="check-row"><input type="checkbox" checked={settings.enabled} onChange={(event) => updateSettings({ ...settings, enabled: event.target.checked })} />自动学习黑话</label><span className="muted">每 {settings.min_messages} 条群消息触发一次，冷却 {settings.cooldown_seconds} 秒</span></div><div className="slang-settings review-settings"><SelectField label="自动审核接口" value={reviewDraft.review_provider_id} options={['', ...(snapshot.interfaces?.providers || []).map((p) => p.id)]} labels={['不审核（新词保持待审核）', ...(snapshot.interfaces?.providers || []).map((p) => providerLabel(p))]} onChange={(value) => setReviewDraft({ ...reviewDraft, review_provider_id: value })} /><Field label="审核模型（可选）" value={reviewDraft.review_model} onChange={(value) => setReviewDraft({ ...reviewDraft, review_model: value })} placeholder="留空使用接口默认模型" /><button className="soft-button" onClick={saveReviewSettings}>保存审核配置</button>{!settings.review_configured && <span className="form-error"><CircleAlert size={15} />未配置审核接口，新词将保持待审核</span>}<span className="muted">研究完成后自动判定：有效解释放行，无效词条直接删除；接口故障时保持待审核。</span></div><div className="data-table">{slang.length ? slang.map((row) => <div className="data-row slang-row" key={row.id}><div className="identity-cell"><span className="capability-icon"><MessageSquareText size={16} /></span><div><strong>{row.term}</strong><small>{row.status === 'confirmed' ? '已确认' : row.status === 'rejected' ? '已忽略' : '待审核'}{row.reviewer ? ` · ${row.reviewer === 'auto' ? '自动放行' : row.reviewer === 'manual' ? '人工复议' : '审核未判定'}` : ''}</small></div></div><div><span className="cell-label">含义</span><span>{row.meaning || '尚未补充'}{row.review_reason ? ` · ${row.review_reason}` : ''}</span></div><div className="row-actions"><button className="soft-button" onClick={() => reviewSlang(row)}>{row.status === 'confirmed' ? '标为待审核' : '确认词条'}</button><button className="icon-button" title="编辑" onClick={() => setEditor({ ...row })}><Pencil size={15} /></button><button className="icon-button danger" title="删除" onClick={() => removeSlang(row.id)}><Trash2 size={15} /></button></div></div>) : <Empty title="还没有黑话词条" detail="自动学习或手动添加的群聊用语会显示在这里。" />}</div></>}
    </section>
    {(showMemoryEditor || editor?.queueId) && <Modal title={editor.queueId ? '编辑待审核记忆' : `${tab === 'global' ? '全局' : 'Bot'} Memory`} onClose={() => setEditor(null)}><div className="form-grid two"><Field label="稳定名称" value={editor.name} onChange={(value) => setEditor({ ...editor, name: value })} placeholder="例如 project-guidelines" /><Field label="标题" value={editor.title} onChange={(value) => setEditor({ ...editor, title: value })} /><Field label="类型" value={editor.type} onChange={(value) => setEditor({ ...editor, type: value })} /><Field label="说明" value={editor.description} onChange={(value) => setEditor({ ...editor, description: value })} /><Field label="记忆内容" wide type="textarea" value={editor.content} onChange={(value) => setEditor({ ...editor, content: value })} /></div><ModalFooter onClose={() => setEditor(null)} onSave={saveMemory} /></Modal>}
    {editor && tab === 'slang' && <Modal title={editor.id ? '编辑黑话词条' : '新增黑话词条'} onClose={() => setEditor(null)}><div className="form-grid two"><Field label="黑话" value={editor.term} onChange={(value) => setEditor({ ...editor, term: value })} /><Field label="含义" wide type="textarea" value={editor.meaning} onChange={(value) => setEditor({ ...editor, meaning: value })} /></div>{error && <div className="form-error"><CircleAlert size={15} />{error}</div>}<ModalFooter onClose={() => setEditor(null)} onSave={saveSlang} /></Modal>}
  </div>;
}

function Memes({ token, tools, onNavigate, onRefresh }) {
  const [rows, setRows] = useState([]); const [settings, setSettings] = useState({ upload_enabled: true, max_bytes: 0 });
  const [query, setQuery] = useState(''); const [thumbs, setThumbs] = useState({});
  const [editor, setEditor] = useState(null); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const thumbsRef = useRef({});
  async function reload() {
    const [list, config] = await Promise.all([api(token, '/memes'), api(token, '/memes/settings')]);
    setRows(list); setSettings(config); setError('');
    const next = {};
    await Promise.all(list.map(async (row) => {
      try { next[row.file] = URL.createObjectURL(await apiBlob(token, `/memes/image/${encodeURIComponent(row.file)}`)); }
      catch { /* 缩略图失败时保留占位图标 */ }
    }));
    Object.values(thumbsRef.current).forEach((url) => URL.revokeObjectURL(url));
    thumbsRef.current = next; setThumbs(next);
  }
  useEffect(() => {
    reload().catch((err) => setError(err.message));
    return () => { Object.values(thumbsRef.current).forEach((url) => URL.revokeObjectURL(url)); thumbsRef.current = {}; };
  }, [token]);
  async function upload(event) {
    const file = event.target.files?.[0]; if (!file) return;
    if (settings.max_bytes && file.size > settings.max_bytes) { setError('图片超过大小限制'); return; }
    setBusy(true); setError('');
    try {
      const data = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = reject; reader.readAsDataURL(file); });
      await api(token, '/memes', 'POST', { name: file.name.replace(/\.[^.]+$/, ''), data });
      await reload(); await onRefresh();
    } catch (err) { setError(err.message); } finally { setBusy(false); event.target.value = ''; }
  }
  async function saveEditor() {
    try {
      await api(token, `/memes/${encodeURIComponent(editor.file)}`, 'PUT', { name: editor.name.trim(), keywords: editor.keywords, summary: editor.summary });
      setEditor(null); await reload();
    } catch (err) { setError(err.message); }
  }
  async function remove(row) {
    if (!window.confirm(`确认删除表情包“${row.name}”？`)) return;
    try { await api(token, `/memes/${encodeURIComponent(row.file)}`, 'DELETE'); await reload(); }
    catch (err) { setError(err.message); }
  }
  async function toggleUpload(checked) {
    try { setSettings(await api(token, '/memes/settings', 'PUT', { upload_enabled: checked })); }
    catch (err) { setError(err.message); }
  }
  const visible = query.trim() ? rows.filter((row) => `${row.name} ${(row.keywords || []).join(' ')} ${row.summary}`.toLowerCase().includes(query.trim().toLowerCase())) : rows;
  const memeTools = ['chat_list_memes', 'chat_save_meme', 'chat_send_meme'];
  return <div className="page-stack">
    <PageIntro kicker="MEME LIBRARY" title="表情包" detail={error || `${rows.length} 张表情；上传后可在聊天里通过 chat_send_meme 发送。`} action="上传图片" onClick={() => document.getElementById('meme-file-input')?.click()} />
    <input id="meme-file-input" type="file" accept="image/png,image/jpeg,image/gif,image/webp" hidden disabled={busy || !settings.upload_enabled} onChange={upload} />
    <section className="surface">
      <div className="slang-settings"><input aria-label="搜索表情包" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索名称、关键词或简介" /><button className="soft-button" disabled={busy || !settings.upload_enabled} onClick={() => document.getElementById('meme-file-input')?.click()}><Upload size={14} />选择图片</button><label className="check-row"><input type="checkbox" checked={settings.upload_enabled} onChange={(event) => toggleUpload(event.target.checked)} />允许新增表情包（WebUI 与 chat_save_meme）</label><span className="muted">单图上限 {Math.round((settings.max_bytes || 0) / 1024)} KB · {busy ? '上传中…' : '就绪'}</span></div>
      <div className="meme-grid">{visible.length ? visible.map((row) => <div className="meme-card" key={row.file}>
        <div className="meme-thumb">{thumbs[row.file] ? <img src={thumbs[row.file]} alt={row.name} /> : <ImageIcon size={22} />}</div>
        <div className="meme-meta"><strong>{row.name}</strong><small>{row.file} · {row.bytes} B</small><span>{row.summary || '暂无简介'}</span><div className="meme-tags">{(row.keywords || []).map((keyword) => <span className="soft-tag" key={keyword}>{keyword}</span>)}</div></div>
        <div className="row-actions"><button className="icon-button" title="编辑" onClick={() => setEditor({ ...row, keywords: (row.keywords || []).join('、') })}><Pencil size={15} /></button><button className="icon-button danger" title="删除" onClick={() => remove(row)}><Trash2 size={15} /></button></div>
      </div>) : <Empty title="还没有表情包" detail="上传图片，或让 Bot 在聊天里通过 chat_save_meme 保存。" />}</div>
    </section>
    <section className="surface meme-tool-card"><SectionTitle title="工具开关" /><p className="muted">在平台账号 / 群聊策略编辑器的「工具默认」中勾选；会话级覆盖使用对话日志里的会话工具设置。</p><div className="inline-actions">{memeTools.map((name) => <span className="soft-tag" key={name}>{name} · {(tools || []).some((tool) => tool.name === name) ? '可用' : '未列出'}</span>)}</div><div className="inline-actions"><button className="soft-button" onClick={() => onNavigate('accounts')}>平台账号</button><button className="soft-button" onClick={() => onNavigate('groups')}>群聊策略</button><button className="soft-button" onClick={() => onNavigate('logs')}>会话工具</button></div></section>
    {editor && <Modal title="编辑表情包" onClose={() => setEditor(null)}><div className="form-grid two"><Field label="名称" value={editor.name} onChange={(value) => setEditor({ ...editor, name: value })} /><Field label="关键词（逗号或顿号分隔）" value={editor.keywords} onChange={(value) => setEditor({ ...editor, keywords: value })} /><Field label="简介" wide type="textarea" value={editor.summary} onChange={(value) => setEditor({ ...editor, summary: value })} /></div>{error && <div className="form-error"><CircleAlert size={15} />{error}</div>}<ModalFooter onClose={() => setEditor(null)} onSave={saveEditor} /></Modal>}
  </div>;
}

function PageIntro({ kicker, title, detail, action, onClick }) { return <div className="page-intro"><div><span className="kicker">{kicker}</span><h2 className="page-heading">{title}</h2><p className="muted intro-detail">{detail}</p></div>{action && <button className="primary-button" onClick={onClick}><Plus size={16} />{action}</button>}</div>; }
function Modal({ title, onClose, children }) { return <div className="modal-backdrop" role="presentation" onMouseDown={(e) => e.target === e.currentTarget && onClose()}><div className="modal"><div className="modal-head"><div><span className="kicker">CONFIGURATION</span><h2>{title}</h2></div><button className="icon-button" onClick={onClose} aria-label="关闭"><X size={17} /></button></div>{children}</div></div>; }
function ModalFooter({ onClose, onSave, busy = false }) { return <div className="modal-footer"><button className="secondary-button" onClick={onClose} disabled={busy}>取消</button><button className="primary-button" onClick={onSave} disabled={busy}><Check size={15} />{busy ? '保存中…' : '保存设置'}</button></div>; }
function Field({ label, value, onChange, placeholder, type = 'text', wide = false, min, max, step }) { return <label className={`field ${wide ? 'wide' : ''}`}><span>{label}</span>{type === 'textarea' ? <textarea value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} /> : <input type={type} value={value} min={min} max={max} step={step} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} />}</label>; }
function SelectField({ label, value, options, labels, onChange }) { return <label className="field"><span>{label}</span><select value={value} onChange={(e) => onChange(e.target.value)}>{options.map((option, index) => <option key={option} value={option}>{labels?.[index] || option || '默认'}</option>)}</select></label>; }

export default App;
