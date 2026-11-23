import { useState } from 'react';
import { CircleAlert, RefreshCw } from 'lucide-react';
import Modal, { ModalFooter } from '../../components/ui/Modal.jsx';
import { Field, SelectField } from '../../components/ui/Field.jsx';
import Button from '../../components/ui/Button.jsx';
import { api } from '../../lib/api.js';
import { modelId } from '../../lib/format.js';
import './ModelConcurrencyTable.css';

const FIELD_LABELS = {
  skills: ['Skill 名称', '描述'],
  mcps: ['MCP 名称', '服务地址'],
  rules: ['Rule 名称', '规则内容'],
};

const CONTENT_KEYS = { mcps: 'url', rules: 'content', skills: 'description' };

export default function CapabilityEditor({ token, kind, value, onClose, onSave }) {
  // 后端只回显密钥末 4 位，输入框保持空白：不填 = 沿用已存密钥。
  const [form, setForm] = useState({ ...value, api_key: '' });
  const [clearKey, setClearKey] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const hasStoredKey = Boolean(value.api_key);

  const set = (key, next) => setForm((previous) => ({ ...previous, [key]: next }));

  async function discover() {
    setBusy(true);
    setError('');
    try {
      const result = await api(token, '/interfaces/providers/discover', 'POST', {
        base_url: form.base_url || '',
        api_key: form.api_key || '',
        provider_id: value.id || '',
      });
      setForm((previous) => ({ ...previous, models: result.models }));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function submit() {
    setSaving(true);
    try {
      const body =
        kind === 'providers'
          ? {
              ...form,
              context_length: Number(form.context_length) || null,
              max_concurrency: form.max_concurrency === '' || form.max_concurrency == null
                ? null
                : Number(form.max_concurrency),
              queue_wait_seconds: form.queue_wait_seconds === '' || form.queue_wait_seconds == null
                ? null
                : Number(form.queue_wait_seconds),
              clear_api_key: clearKey,
            }
          : form;
      await onSave(body);
    } finally {
      setSaving(false);
    }
  }

  if (kind === 'providers') {
    const models = form.models || [];
    const selected = models.find((model) => model.id === modelId(form.model));
    return (
      <Modal
        title={value.id ? '编辑 AI 接口' : '新增 AI 接口'}
        kicker="AI PROVIDER"
        size="lg"
        onClose={onClose}
      >
        <div className="form-grid form-grid--two">
          <Field label="接口名称" value={form.name || ''} onChange={(next) => set('name', next)} />
          <Field
            label="Base URL"
            value={form.base_url || ''}
            onChange={(next) => set('base_url', next)}
            placeholder="https://api.example.com/v1"
          />
          <div className="ui-field">
            <span className="ui-field__label">API Key</span>
            <input
              className="ui-input"
              type="password"
              autoComplete="off"
              value={form.api_key || ''}
              placeholder={hasStoredKey && !clearKey ? '已保存，留空则保持不变' : '粘贴新的 API Key'}
              disabled={clearKey}
              onChange={(event) => set('api_key', event.target.value)}
            />
            {hasStoredKey ? (
              <span className="ui-field__hint">
                <label className="ui-check">
                  <input
                    type="checkbox"
                    checked={clearKey}
                    onChange={(event) => {
                      setClearKey(event.target.checked);
                      if (event.target.checked) set('api_key', '');
                    }}
                  />
                  清除已保存的 Key
                </label>
              </span>
            ) : (
              <span className="ui-field__hint">保存后只会显示末 4 位。</span>
            )}
          </div>
          <Field
            label="备用上下文大小"
            type="number"
            value={form.context_length || ''}
            onChange={(next) => set('context_length', next)}
            placeholder="远端未提供时使用"
          />
          <Field
            label="接口默认并发数"
            type="number"
            min={1}
            max={64}
            value={form.max_concurrency ?? ''}
            onChange={(next) => set('max_concurrency', next)}
            placeholder="留空表示不限制"
            hint="同一接口同时只允许 N 个模型请求，其余按先来后到排队。"
          />
          <Field
            label="排队等待秒数"
            type="number"
            min={1}
            max={600}
            value={form.queue_wait_seconds ?? ''}
            onChange={(next) => set('queue_wait_seconds', next)}
            placeholder="留空则使用默认 120 秒"
            hint="等待超过该时长则放弃本次回复，不会向群里发任何内容。"
          />

          <div className="ui-field ui-field--wide">
            <span className="ui-field__label">远端模型</span>
            <div className="inline-actions">
              <Button variant="soft" size="sm" icon={RefreshCw} loading={busy} onClick={discover}>
                {busy ? '获取中…' : '获取模型'}
              </Button>
              <span className="text-faint">已获取 {models.length} 个模型</span>
            </div>
          </div>

          <SelectField
            label="默认模型"
            value={modelId(form.model)}
            options={['', ...models.map((model) => model.id)]}
            labels={[
              '不设置',
              ...models.map((model) =>
                model.context_length
                  ? `${model.id} · ${model.context_length.toLocaleString()} tokens`
                  : model.id,
              ),
            ]}
            onChange={(next) => set('model', next)}
          />
          <div className="ui-field">
            <span className="ui-field__label">上下文说明</span>
            <span className="ui-field__hint">
              {selected?.context_length
                ? `当前模型远端上下文：${selected.context_length.toLocaleString()} tokens`
                : '当前模型未返回上下文，将使用备用设置或全局设置。'}
            </span>
          </div>

          {models.length ? (
            <div className="ui-field ui-field--wide">
              <span className="ui-field__label">模型并发覆盖（留空则使用接口默认）</span>
              <div className="model-concurrency-table">
                <div className="model-concurrency-table__row model-concurrency-table__row--head">
                  <span>模型 ID</span>
                  <span>并发数</span>
                  <span>排队等待秒数</span>
                </div>
                {models.map((model, index) => (
                  <div key={model.id} className="model-concurrency-table__row">
                    <span title={model.id} className="model-concurrency-table__id">
                      {model.id}
                    </span>
                    <input
                      className="ui-input"
                      type="number"
                      min={1}
                      max={64}
                      placeholder="接口默认"
                      value={model.max_concurrency ?? ''}
                      onChange={(event) =>
                        set('models', models.map((item, itemIndex) =>
                          itemIndex === index
                            ? {
                                ...item,
                                max_concurrency: event.target.value === '' ? null : Number(event.target.value),
                              }
                            : item,
                        ))
                      }
                    />
                    <input
                      className="ui-input"
                      type="number"
                      min={1}
                      max={600}
                      placeholder="接口默认"
                      value={model.queue_wait_seconds ?? ''}
                      onChange={(event) =>
                        set('models', models.map((item, itemIndex) =>
                          itemIndex === index
                            ? {
                                ...item,
                                queue_wait_seconds: event.target.value === '' ? null : Number(event.target.value),
                              }
                            : item,
                        ))
                      }
                    />
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>

        {error ? (
          <div className="form-error">
            <CircleAlert size={15} />
            {error}
          </div>
        ) : null}
        <ModalFooter onClose={onClose} onSave={submit} busy={saving} />
      </Modal>
    );
  }

  const labels = FIELD_LABELS[kind] || ['名称', '内容'];
  const contentKey = CONTENT_KEYS[kind] || 'description';

  return (
    <Modal title={value.id ? '编辑能力' : '新增能力'} kicker="CAPABILITY" onClose={onClose}>
      <div className="form-grid">
        <Field label={labels[0]} value={form.name || ''} onChange={(next) => set('name', next)} />
        <Field
          label={labels[1]}
          wide
          type="textarea"
          value={form[contentKey] || ''}
          onChange={(next) => set(contentKey, next)}
        />
      </div>
      {error ? (
        <div className="form-error">
          <CircleAlert size={15} />
          {error}
        </div>
      ) : null}
      <ModalFooter onClose={onClose} onSave={submit} busy={saving} />
    </Modal>
  );
}
