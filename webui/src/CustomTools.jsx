import { useCallback, useEffect, useState } from 'react';
import {
  Check, CircleAlert, Pencil, Play, Plus, Trash2, Wrench, X,
} from 'lucide-react';

const SCOPES = ['admin', 'private', 'all', 'manual'];
const SCOPE_LABELS = {
  admin: '仅管理员私聊',
  private: '所有私聊',
  all: '所有会话',
  manual: '手动指定群聊',
};
const SCOPE_HINTS = {
  admin: '只有 Agent 模式下的管理员私聊能调用，与内置 Bash 同级。',
  private: '所有已批准的私聊都能调用，包含 Chat 模式。',
  all: '群聊里任何人都可能诱导模型运行该脚本，等同于给群成员一个受限 shell。',
  manual: '默认对所有会话隐藏，仅下面勾选的群聊可见。',
};
const MAX_TOOLS = 40;
const SCHEMA_TEMPLATE = `{
  "type": "object",
  "properties": {
    "target": { "type": "string", "description": "要检查的目标" }
  },
  "required": ["target"]
}`;
const SOURCE_TEMPLATE = `"""自定义 Tool：在工作区执行命令并整理输出。"""


def run(args, ctx):
    result = run_cmd("git status --porcelain")
    if not result["ok"]:
        return "命令失败：" + result["stderr"]
    lines = [line for line in result["stdout"].splitlines() if line.strip()]
    return f"{len(lines)} 个未提交变更"
`;

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

function Modal({ title, onClose, children }) {
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal modal-editor">
        <div className="modal-head">
          <div><span className="kicker">CUSTOM TOOL</span><h2>{title}</h2></div>
          <button className="icon-button" onClick={onClose} aria-label="关闭"><X size={17} /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

function ModalFooter({ onClose, onSave, busy = false }) {
  return (
    <div className="modal-footer">
      <button className="secondary-button" onClick={onClose} disabled={busy}>取消</button>
      <button className="primary-button" onClick={onSave} disabled={busy}>
        <Check size={15} />{busy ? '处理中…' : '保存设置'}
      </button>
    </div>
  );
}

function Field({ label, value, onChange, placeholder, type = 'text', wide = false, min, max, step }) {
  return (
    <label className={`field ${wide ? 'wide' : ''}`}>
      <span>{label}</span>
      {type === 'textarea'
        ? <textarea value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} />
        : <input type={type} value={value} min={min} max={max} step={step} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} />}
    </label>
  );
}

function SelectField({ label, value, options, labels, onChange }) {
  return (
    <label className="field">
      <span>{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((option, index) => <option key={option} value={option}>{labels?.[index] || option}</option>)}
      </select>
    </label>
  );
}

function emptyForm() {
  return {
    name: '', description: '', scope: 'admin', timeout: 30, enabled: true,
    schemaText: SCHEMA_TEMPLATE, source: SOURCE_TEMPLATE, argsText: '{}',
    allowedGroups: [],
  };
}

function parseJson(text, label) {
  try {
    return { value: JSON.parse(text || '{}') };
  } catch {
    return { error: `${label}不是合法 JSON` };
  }
}

function Editor({ token, groups, toolId, onClose, onSaved }) {
  const [form, setForm] = useState(emptyForm);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(Boolean(toolId));
  const [error, setError] = useState('');
  const [runResult, setRunResult] = useState(null);
  const set = (key, next) => setForm((previous) => ({ ...previous, [key]: next }));

  useEffect(() => {
    if (!toolId) return undefined;
    let alive = true;
    api(token, `/custom-tools/${toolId}`)
      .then((row) => {
        if (!alive) return;
        setForm({
          name: String(row.name || '').replace(/^custom_/, ''),
          description: row.description || '',
          scope: row.scope || 'admin',
          timeout: row.timeout || 30,
          enabled: row.enabled !== false,
          schemaText: JSON.stringify(row.input_schema || { type: 'object', properties: {} }, null, 2),
          source: row.source || '',
          argsText: '{}',
          allowedGroups: Array.isArray(row.allowed_groups) ? row.allowed_groups : [],
        });
        if (row.status === 'invalid' && row.error) setError(row.error);
      })
      .catch((err) => { if (alive) setError(err.message); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [token, toolId]);

  function fullName() {
    const suffix = form.name.trim().replace(/^custom_/, '').toLowerCase();
    return suffix ? `custom_${suffix}` : '';
  }

  async function save() {
    if (!fullName()) { setError('工具名不能为空'); return; }
    const parsed = parseJson(form.schemaText, '参数 Schema ');
    if (parsed.error) { setError(parsed.error); return; }
    setBusy(true); setError('');
    const body = {
      name: fullName(),
      description: form.description,
      scope: form.scope,
      timeout: Number(form.timeout) || 30,
      enabled: form.enabled,
      input_schema: parsed.value,
      source: form.source,
      allowed_groups: form.scope === 'manual' ? form.allowedGroups : [],
    };
    try {
      if (toolId) await api(token, `/custom-tools/${toolId}`, 'PUT', body);
      else await api(token, '/custom-tools', 'POST', body);
      await onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function test() {
    const parsed = parseJson(form.argsText, '测试参数 ');
    if (parsed.error) { setError(parsed.error); return; }
    setBusy(true); setError(''); setRunResult(null);
    try {
      setRunResult(await api(token, '/custom-tools/test', 'POST', {
        source: form.source,
        name: fullName() || 'custom_draft',
        args: parsed.value,
        timeout: Number(form.timeout) || 30,
      }));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  function groupKey(group) {
    return `${group.platform} ${group.bot_id} ${group.group_id}`;
  }

  function toggleGroup(group) {
    const triple = {
      platform: String(group.platform || ''),
      bot_id: String(group.bot_id || ''),
      group_id: String(group.group_id || ''),
    };
    const current = form.allowedGroups;
    const selected = current.some((item) => groupKey(item) === groupKey(triple));
    set('allowedGroups', selected
      ? current.filter((item) => groupKey(item) !== groupKey(triple))
      : [...current, triple]);
  }

  if (loading) {
    return <Modal title="加载中…" onClose={onClose}><p className="muted">正在读取脚本…</p></Modal>;
  }

  return (
    <Modal title={toolId ? '编辑自定义 Tool' : '新增自定义 Tool'} onClose={onClose}>
      <div className="form-grid two">
        <label className="field">
          <span>工具名</span>
          <div className="prefix-input">
            <span className="prefix-chip">custom_</span>
            <input value={form.name} onChange={(e) => set('name', e.target.value)} placeholder="disk_usage" />
          </div>
        </label>
        <SelectField
          label="可见范围"
          value={form.scope}
          options={SCOPES}
          labels={SCOPES.map((scope) => SCOPE_LABELS[scope])}
          onChange={(value) => set('scope', value)}
        />
        <Field label="描述（模型据此判断何时调用）" wide value={form.description} onChange={(value) => set('description', value)} placeholder="检查工作区的未提交变更并汇总" />
        <Field label="超时（秒）" type="number" min={1} max={300} value={form.timeout} onChange={(value) => set('timeout', value)} />
        <div className="field">
          <span>状态</span>
          <label className="check-row">
            <input type="checkbox" checked={form.enabled} onChange={(e) => set('enabled', e.target.checked)} />
            启用这个工具
          </label>
        </div>
        <div className="field wide">
          <span>范围说明</span>
          <span className="inline-note">{SCOPE_HINTS[form.scope]}</span>
        </div>
        {form.scope === 'manual' && (
          <div className="field wide">
            <span>允许的群聊（至少选一个）</span>
            {groups.length ? (
              <div className="tool-check-grid">
                {groups.map((group) => {
                  const selected = form.allowedGroups.some((item) => groupKey(item) === groupKey(group));
                  const label = `${group.name || group.group_id} · ${group.platform}/${group.bot_id} · ${group.group_id}`;
                  return (
                    <label key={group.id} className="check-row" title={label}>
                      <input type="checkbox" checked={selected} onChange={() => toggleGroup(group)} />
                      <span>{label}</span>
                    </label>
                  );
                })}
              </div>
            ) : (
              <span className="inline-note">还没有群聊策略，请先在「群聊策略」里添加。</span>
            )}
          </div>
        )}
        <label className="field wide">
          <span>参数 Schema（JSON Schema）</span>
          <textarea className="code-area short" value={form.schemaText} onChange={(e) => set('schemaText', e.target.value)} spellCheck={false} />
        </label>
        <label className="field wide">
          <span>脚本内容</span>
          <textarea className="code-area" value={form.source} onChange={(e) => set('source', e.target.value)} spellCheck={false} />
        </label>
        <div className="field wide">
          <span>脚本约定</span>
          <span className="inline-note">
            必须定义同步函数 <code>run(args, ctx)</code> 并返回字符串。用
            <code> run_cmd(&quot;命令&quot;)</code> 在工作区执行命令（返回 code / stdout / stderr），
            用 <code>log(&quot;...&quot;)</code> 记录调试信息。脚本以独立子进程运行，
            环境变量已剥离密钥类变量，超时后连同子进程一并终止。
          </span>
        </div>
        <label className="field wide">
          <span>测试参数（JSON）</span>
          <textarea className="code-area short" value={form.argsText} onChange={(e) => set('argsText', e.target.value)} spellCheck={false} />
        </label>
        <div className="field wide">
          <span>试运行</span>
          <div className="inline-actions">
            <button className="soft-button" disabled={busy} onClick={test}><Play size={14} />测试运行</button>
            <span className="muted">不会保存，也不会写入活动日志。</span>
          </div>
        </div>
        {runResult && (
          <div className="field wide">
            <span>{runResult.ok ? '运行结果' : '运行失败'}</span>
            <pre className={`test-output${runResult.ok ? '' : ' error'}`}>
              {runResult.ok
                ? (runResult.output || '(no output)')
                : `${runResult.error}\n${runResult.traceback || ''}`.trim()}
            </pre>
            <span className="inline-note">
              耗时 {runResult.elapsed_ms}ms · 命令 {runResult.commands} 次
              {runResult.truncated ? ' · 输出已截断' : ''}
            </span>
          </div>
        )}
      </div>
      {error && <div className="form-error"><CircleAlert size={15} />{error}</div>}
      <ModalFooter onClose={onClose} onSave={save} busy={busy} />
    </Modal>
  );
}

export default function CustomToolsPanel({ token, onRefresh }) {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState('');
  const [busyId, setBusyId] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setRows(await api(token, '/custom-tools'));
      setError('');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  async function saved() {
    setEditing('');
    await load();
    if (onRefresh) await onRefresh();
  }

  async function toggle(row) {
    setBusyId(row.id); setError('');
    try {
      await api(token, `/custom-tools/${row.id}`, 'PUT', { enabled: !row.enabled });
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId('');
    }
  }

  async function remove(row) {
    if (!window.confirm(`删除 ${row.name}？脚本会一并删除，且不可恢复。`)) return;
    setBusyId(row.id); setError('');
    try {
      await api(token, `/custom-tools/${row.id}`, 'DELETE');
      await load();
      if (onRefresh) await onRefresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId('');
    }
  }

  return (
    <div className="custom-tools">
      <div className="table-toolbar">
        <div>
          <strong>自定义 Tool</strong>
          <span className="muted"> · {rows.length}/{MAX_TOOLS}，只能在这里增改</span>
        </div>
        <button className="primary-button" disabled={rows.length >= MAX_TOOLS} onClick={() => setEditing('new')}>
          <Plus size={15} />新增自定义 Tool
        </button>
      </div>
      {error && <div className="form-error"><CircleAlert size={15} />{error}</div>}
      <div className="data-table">
        {rows.length ? rows.map((row) => (
          <div className="data-row tool-row" key={row.id}>
            <div className="identity-cell">
              <span className="capability-icon"><Wrench size={16} /></span>
              <div>
                <strong>{row.name}</strong>
                <small>{row.description || '尚未填写描述'}</small>
              </div>
            </div>
            <div>
              <span className="cell-label">范围 / 超时</span>
              <span>{SCOPE_LABELS[row.scope] || row.scope} · {row.timeout}s</span>
            </div>
            <div className="row-actions">
              {row.status === 'invalid' && <span className="status-badge disabled"><span />文件异常</span>}
              <button className="soft-button" disabled={busyId === row.id} onClick={() => toggle(row)}>
                {row.enabled ? '停用' : '启用'}
              </button>
              <button className="icon-button" title="编辑" onClick={() => setEditing(row.id)}><Pencil size={15} /></button>
              <button className="icon-button danger" title="删除" onClick={() => remove(row)}><Trash2 size={15} /></button>
            </div>
          </div>
        )) : (
          <div className="empty-state">
            <div className="empty-icon"><Wrench size={19} /></div>
            <strong>{loading ? '正在读取…' : '还没有自定义 Tool'}</strong>
            <span>写一段 Python 脚本，让模型能在工作区执行命令并读取输出。</span>
          </div>
        )}
      </div>
      {editing && (
        <Editor token={token} groups={groups} toolId={editing === 'new' ? '' : editing} onClose={() => setEditing('')} onSaved={saved} />
      )}
    </div>
  );
}
