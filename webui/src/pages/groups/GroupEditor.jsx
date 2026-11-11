import { useState } from 'react';
import Modal, { ModalFooter } from '../../components/ui/Modal.jsx';
import { Field, SelectField } from '../../components/ui/Field.jsx';
import ToolSelection from '../../components/tools/ToolSelection.jsx';
import { modelContext, modelId, providerLabel } from '../../lib/format.js';

export default function GroupEditor({ value, accounts, providers, tools, onClose, onSave }) {
  const bound = accounts.find(
    (account) => account.platform === value.platform && account.bot_id === value.bot_id,
  );
  const [form, setForm] = useState({
    enabled: true,
    reply_probability: 1,
    reasoning_effort: 'medium',
    enabled_tools: null,
    ...value,
    account_id: bound?.id || '',
  });
  const [busy, setBusy] = useState(false);

  const set = (key, next) => setForm((previous) => ({ ...previous, [key]: next }));
  const account = accounts.find((item) => item.id === form.account_id);
  const provider = providers.find((item) => item.id === form.provider_id);
  const models = provider?.models || [];

  async function submit() {
    setBusy(true);
    try {
      await onSave({
        ...form,
        platform: account?.platform || form.platform || '',
        bot_id: account?.bot_id || form.bot_id || '',
        enabled: form.enabled !== false,
        reply_probability: form.reply_probability ?? 1,
        cost_limit: form.cost_limit === '' ? null : Number(form.cost_limit) || null,
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title={value.id ? '编辑群聊策略' : '添加群聊策略'}
      kicker="GROUP POLICY"
      size="lg"
      onClose={onClose}
    >
      <div className="form-grid form-grid--two">
        <SelectField
          label="绑定账号"
          value={form.account_id}
          options={['', ...accounts.map((item) => item.id)]}
          labels={[
            '选择账号',
            ...accounts.map((item) => `${item.name || item.bot_id} · ${item.platform}`),
          ]}
          onChange={(next) => {
            const target = accounts.find((item) => item.id === next);
            setForm({
              ...form,
              account_id: next,
              platform: target?.platform || '',
              bot_id: target?.bot_id || '',
            });
          }}
        />
        <Field
          label="群 ID"
          value={form.group_id || ''}
          onChange={(next) => set('group_id', next)}
          placeholder="群号或会话 ID"
        />
        <Field
          label="群名称"
          value={form.name || ''}
          onChange={(next) => set('name', next)}
          placeholder="留空则使用群 ID"
        />
        <SelectField
          label="思考强度"
          value={form.reasoning_effort || 'medium'}
          options={['low', 'medium', 'high']}
          labels={['低', '中', '高']}
          onChange={(next) => set('reasoning_effort', next)}
        />
        <SelectField
          label="AI 供应商"
          value={form.provider_id || ''}
          options={['', ...providers.map((item) => item.id)]}
          labels={['跟随账号', ...providers.map(providerLabel)]}
          onChange={(next) => set('provider_id', next)}
        />
        <SelectField
          label="模型"
          value={modelId(form.model)}
          options={['', ...models.map((item) => item.id)]}
          labels={[
            '供应商默认',
            ...models.map((item) =>
              modelContext(item) ? `${item.id} · ${modelContext(item).toLocaleString()} tokens` : item.id,
            ),
          ]}
          onChange={(next) => set('model', next)}
        />
        <Field
          label="回复概率（0 永不回复 · 1 一直回复）"
          type="number"
          min={0}
          max={1}
          step={0.05}
          value={form.reply_probability ?? 1}
          onChange={(next) => set('reply_probability', next)}
        />
        <Field
          label="成本上限（可选）"
          type="number"
          value={form.cost_limit ?? ''}
          onChange={(next) => set('cost_limit', next)}
          placeholder="留空表示不限制"
        />
        <Field
          label="群聊提示词（完整覆盖账号人格）"
          wide
          type="textarea"
          rows={8}
          value={form.system_prompt || ''}
          onChange={(next) => set('system_prompt', next)}
          placeholder="留空则继承账号人格模板和补充提示。"
        />
      </div>

      <ToolSelection
        value={form.enabled_tools}
        tools={tools}
        onChange={(next) => set('enabled_tools', next)}
      />

      <ModalFooter onClose={onClose} onSave={submit} busy={busy} />
    </Modal>
  );
}
