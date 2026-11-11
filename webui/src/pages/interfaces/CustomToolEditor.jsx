import { useEffect, useState } from 'react';
import { CircleAlert, Play } from 'lucide-react';
import Modal, { ModalFooter } from '../../components/ui/Modal.jsx';
import { CheckRow, Field, SelectField } from '../../components/ui/Field.jsx';
import Button from '../../components/ui/Button.jsx';
import { api } from '../../lib/api.js';
import './CustomToolEditor.css';

export const SCOPES = ['admin', 'private', 'all', 'manual'];

export const SCOPE_LABELS = {
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

export const MAX_TOOLS = 40;

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

function emptyForm() {
  return {
    name: '',
    description: '',
    scope: 'admin',
    timeout: 30,
    enabled: true,
    schemaText: SCHEMA_TEMPLATE,
    source: SOURCE_TEMPLATE,
    argsText: '{}',
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

function groupKey(group) {
  return `${group.platform} ${group.bot_id} ${group.group_id}`;
}

export default function CustomToolEditor({ token, groups = [], toolId, onClose, onSaved }) {
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
      .catch((err) => {
        if (alive) setError(err.message);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [token, toolId]);

  function fullName() {
    const suffix = form.name.trim().replace(/^custom_/, '').toLowerCase();
    return suffix ? `custom_${suffix}` : '';
  }

  async function save() {
    if (!fullName()) {
      setError('工具名不能为空');
      return;
    }
    const parsed = parseJson(form.schemaText, '参数 Schema ');
    if (parsed.error) {
      setError(parsed.error);
      return;
    }
    setBusy(true);
    setError('');
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
    if (parsed.error) {
      setError(parsed.error);
      return;
    }
    setBusy(true);
    setError('');
    setRunResult(null);
    try {
      setRunResult(
        await api(token, '/custom-tools/test', 'POST', {
          source: form.source,
          name: fullName() || 'custom_draft',
          args: parsed.value,
          timeout: Number(form.timeout) || 30,
        }),
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  function toggleGroup(group) {
    const triple = {
      platform: String(group.platform || ''),
      bot_id: String(group.bot_id || ''),
      group_id: String(group.group_id || ''),
    };
    const current = form.allowedGroups;
    const selected = current.some((item) => groupKey(item) === groupKey(triple));
    set(
      'allowedGroups',
      selected
        ? current.filter((item) => groupKey(item) !== groupKey(triple))
        : [...current, triple],
    );
  }

  if (loading) {
    return (
      <Modal title="加载中…" kicker="CUSTOM TOOL" size="xl" onClose={onClose}>
        <p className="text-muted">正在读取脚本…</p>
      </Modal>
    );
  }

  return (
    <Modal
      title={toolId ? '编辑自定义 Tool' : '新增自定义 Tool'}
      kicker="CUSTOM TOOL"
      size="xl"
      onClose={onClose}
    >
      <div className="form-grid form-grid--two">
        <label className="ui-field">
          <span className="ui-field__label">工具名</span>
          <span className="prefix-input">
            <span className="prefix-chip">custom_</span>
            <input
              className="ui-input"
              value={form.name}
              placeholder="disk_usage"
              onChange={(event) => set('name', event.target.value)}
            />
          </span>
        </label>

        <SelectField
          label="可见范围"
          value={form.scope}
          options={SCOPES}
          labels={SCOPES.map((scope) => SCOPE_LABELS[scope])}
          onChange={(next) => set('scope', next)}
        />

        <Field
          label="描述（模型据此判断何时调用）"
          wide
          value={form.description}
          onChange={(next) => set('description', next)}
          placeholder="检查工作区的未提交变更并汇总"
        />

        <Field
          label="超时（秒）"
          type="number"
          min={1}
          max={300}
          value={form.timeout}
          onChange={(next) => set('timeout', next)}
        />

        <div className="form-note">
          <CheckRow
            label="启用这个工具"
            checked={form.enabled}
            onChange={(checked) => set('enabled', checked)}
          />
        </div>

        <div className="ui-field ui-field--wide">
          <span className="ui-field__label">范围说明</span>
          <span className="ui-field__hint">{SCOPE_HINTS[form.scope]}</span>
        </div>

        {form.scope === 'manual' ? (
          <div className="ui-field ui-field--wide">
            <span className="ui-field__label">允许的群聊（至少选一个）</span>
            {groups.length ? (
              <div className="custom-tool__groups">
                {groups.map((group) => {
                  const selected = form.allowedGroups.some(
                    (item) => groupKey(item) === groupKey(group),
                  );
                  const label = `${group.name || group.group_id} · ${group.platform}/${group.bot_id} · ${group.group_id}`;
                  return (
                    <CheckRow
                      key={group.id}
                      label={label}
                      title={label}
                      checked={selected}
                      onChange={() => toggleGroup(group)}
                    />
                  );
                })}
              </div>
            ) : (
              <span className="ui-field__hint">还没有群聊策略，请先在「群聊策略」里添加。</span>
            )}
          </div>
        ) : null}

        <Field
          label="参数 Schema（JSON Schema）"
          wide
          type="textarea"
          rows={7}
          code
          value={form.schemaText}
          onChange={(next) => set('schemaText', next)}
        />

        <Field
          label="脚本内容"
          wide
          type="textarea"
          rows={14}
          code
          value={form.source}
          onChange={(next) => set('source', next)}
        />

        <div className="ui-field ui-field--wide">
          <span className="ui-field__label">脚本约定</span>
          <span className="inline-note">
            必须定义同步函数 <code>run(args, ctx)</code> 并返回字符串。用
            <code>run_cmd(&quot;命令&quot;)</code> 在工作区执行命令（返回 code / stdout / stderr），用
            <code>log(&quot;...&quot;)</code> 记录调试信息。脚本以独立子进程运行，环境变量已剥离密钥类变量，超时后连同子进程一并终止。
          </span>
        </div>

        <Field
          label="测试参数（JSON）"
          wide
          type="textarea"
          rows={4}
          code
          value={form.argsText}
          onChange={(next) => set('argsText', next)}
        />

        <div className="ui-field ui-field--wide">
          <span className="ui-field__label">试运行</span>
          <div className="inline-actions">
            <Button variant="soft" size="sm" icon={Play} loading={busy} onClick={test}>
              测试运行
            </Button>
            <span className="text-faint">不会保存，也不会写入活动日志。</span>
          </div>
        </div>

        {runResult ? (
          <div className="ui-field ui-field--wide">
            <span className="ui-field__label">{runResult.ok ? '运行结果' : '运行失败'}</span>
            <pre className={`code-block${runResult.ok ? '' : ' code-block--error'}`}>
              {runResult.ok
                ? runResult.output || '(no output)'
                : `${runResult.error}\n${runResult.traceback || ''}`.trim()}
            </pre>
            <span className="ui-field__hint">
              耗时 {runResult.elapsed_ms}ms · 命令 {runResult.commands} 次
              {runResult.truncated ? ' · 输出已截断' : ''}
            </span>
          </div>
        ) : null}
      </div>

      {error ? (
        <div className="form-error">
          <CircleAlert size={15} />
          {error}
        </div>
      ) : null}

      <ModalFooter onClose={onClose} onSave={save} busy={busy} saveLabel="保存工具" />
    </Modal>
  );
}
