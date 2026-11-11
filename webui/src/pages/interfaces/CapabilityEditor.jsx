import { useState } from 'react';
import { CircleAlert, RefreshCw } from 'lucide-react';
import Modal, { ModalFooter } from '../../components/ui/Modal.jsx';
import { Field, SelectField } from '../../components/ui/Field.jsx';
import Button from '../../components/ui/Button.jsx';
import { api } from '../../lib/api.js';
import { modelId } from '../../lib/format.js';

const FIELD_LABELS = {
  skills: ['Skill 名称', '描述'],
  mcps: ['MCP 名称', '服务地址'],
  rules: ['Rule 名称', '规则内容'],
};

const CONTENT_KEYS = { mcps: 'url', rules: 'content', skills: 'description' };

export default function CapabilityEditor({ token, kind, value, onClose, onSave }) {
  const [form, setForm] = useState({ ...value });
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const set = (key, next) => setForm((previous) => ({ ...previous, [key]: next }));

  async function discover() {
    setBusy(true);
    setError('');
    try {
      const result = await api(token, '/interfaces/providers/discover', 'POST', {
        base_url: form.base_url || '',
        api_key: form.api_key || '',
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
          ? { ...form, context_length: Number(form.context_length) || null }
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
          <Field
            label="API Key"
            type="password"
            value={form.api_key || ''}
            onChange={(next) => set('api_key', next)}
            autoComplete="off"
          />
          <Field
            label="备用上下文大小"
            type="number"
            value={form.context_length || ''}
            onChange={(next) => set('context_length', next)}
            placeholder="远端未提供时使用"
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
