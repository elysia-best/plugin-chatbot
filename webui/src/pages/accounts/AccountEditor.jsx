import { useState } from 'react';
import { CircleAlert } from 'lucide-react';
import Modal, { ModalFooter } from '../../components/ui/Modal.jsx';
import { CheckRow, Field, SelectField } from '../../components/ui/Field.jsx';
import ToolSelection from '../../components/tools/ToolSelection.jsx';
import AccessLists from './AccessLists.jsx';
import { modelContext, modelId, providerLabel } from '../../lib/format.js';

const EFFORT_LABELS = ['低', '中', '高'];

export default function AccountEditor({ value, roles, tools, providers, snapshot, onClose, onSave }) {
  const [form, setForm] = useState({
    enabled: true,
    reasoning_effort: 'medium',
    temperature_enabled: true,
    temperature: 0.7,
    persona_role: '',
    provider_id: '',
    enabled_tools: null,
    ...value,
  });
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState('');

  const set = (key, next) => setForm((previous) => ({ ...previous, [key]: next }));

  const provider = providers.find((item) => item.id === form.provider_id);
  const models = provider?.models || [];
  const selectedModel = models.find((item) => item.id === modelId(form.model));
  const contextHint = modelContext(selectedModel)
    ? `当前模型：${modelContext(selectedModel).toLocaleString()} tokens（远端识别）`
    : provider
      ? '当前模型未提供上下文，将使用备用设置或全局设置。'
      : '请先在「接口能力」中配置 AI 接口。';

  function selectProvider(providerId) {
    const nextProvider = providers.find((item) => item.id === providerId);
    const currentModel = modelId(form.model);
    const stillAvailable = nextProvider?.models?.some((item) => item.id === currentModel);
    setForm((previous) => ({
      ...previous,
      provider_id: providerId,
      model: stillAvailable ? currentModel : modelId(nextProvider?.model),
    }));
  }

  async function submit() {
    setSaving(true);
    setSaveError('');
    try {
      const { base_url: _baseUrl, api_key: _apiKey, ...payload } = form;
      await onSave({
        ...payload,
        provider_id: form.provider_id || '',
        model: modelId(form.model),
        context_length: Number(form.context_length) || null,
        enabled: form.enabled !== false,
      });
    } catch (error) {
      setSaveError(error?.message || '账号设置保存失败');
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      title={value.id ? '编辑平台账号' : '新增平台账号'}
      kicker="PLATFORM ACCOUNT"
      size="xl"
      onClose={onClose}
    >
      <div className="form-grid form-grid--two">
        <Field
          label="账号名称"
          value={form.name || ''}
          onChange={(next) => set('name', next)}
          placeholder="留空则使用 Bot ID"
        />
        <Field
          label="平台 / adapter"
          value={form.platform || ''}
          onChange={(next) => set('platform', next)}
          placeholder="onebot / qq / satori"
        />
        <Field label="Bot ID" value={form.bot_id || ''} onChange={(next) => set('bot_id', next)} />

        <SelectField
          label="AI 接口"
          value={form.provider_id || ''}
          options={['', ...providers.map((item) => item.id)]}
          labels={['选择已配置接口', ...providers.map(providerLabel)]}
          onChange={selectProvider}
        />
        <SelectField
          label="模型"
          value={modelId(form.model)}
          options={['', ...models.map((item) => item.id)]}
          labels={[
            '使用接口默认模型',
            ...models.map((item) => {
              const context = modelContext(item);
              return context ? `${item.id} · ${context.toLocaleString()} tokens` : item.id;
            }),
          ]}
          onChange={(next) => set('model', next)}
        />
        <SelectField
          label="思考强度"
          value={form.reasoning_effort || 'medium'}
          options={['low', 'medium', 'high']}
          labels={EFFORT_LABELS}
          onChange={(next) => set('reasoning_effort', next)}
        />
        <Field
          label="Temperature（0–2）"
          type="number"
          value={form.temperature ?? 0.7}
          onChange={(next) => set('temperature', next)}
          placeholder="默认 0.7"
        />
        <div className="form-note">
          <CheckRow
            label="启用 Temperature 参数"
            description="部分模型不兼容该参数，如遇报错请关闭。"
            checked={form.temperature_enabled !== false}
            onChange={(checked) => set('temperature_enabled', checked)}
          />
        </div>

        <Field
          label="备用上下文大小"
          type="number"
          value={form.context_length || ''}
          onChange={(next) => set('context_length', next)}
          placeholder="接口模型没有提供时使用"
        />
        <div className="ui-field">
          <span className="ui-field__label">接口上下文</span>
          <span className="ui-field__hint">{contextHint}</span>
        </div>

        <SelectField
          label="人格模板"
          value={form.persona_role || ''}
          options={['', ...roles.map((role) => role.name)]}
          labels={['全局默认', ...roles.map((role) => role.name)]}
          onChange={(next) => set('persona_role', next)}
        />
        <div className="ui-field" />

        <Field
          label="账号补充提示"
          wide
          type="textarea"
          value={form.persona_prompt || ''}
          onChange={(next) => set('persona_prompt', next)}
          placeholder="追加在人格模板之后的说话规则"
        />
        <Field
          label="禁用称谓 / 口癖黑名单（换行或逗号分隔）"
          wide
          type="textarea"
          value={
            Array.isArray(form.persona_banned)
              ? form.persona_banned.join('\n')
              : form.persona_banned || ''
          }
          onChange={(next) =>
            set(
              'persona_banned',
              next
                .split(/[\n,，、]+/)
                .map((item) => item.trim())
                .filter(Boolean),
            )
          }
          placeholder="例如：本鲸（其他 Bot 的自称）。命中时丢弃该条回复并重试一次。"
        />

        <div className="form-note form-note--wide">
          <CheckRow
            label="为此 Bot 自动整理记忆草稿"
            checked={form.memory_enabled !== false}
            onChange={(checked) => set('memory_enabled', checked)}
          />
        </div>
        <Field
          label="每收到多少条消息后总结"
          type="number"
          value={form.memory_interval ?? 50}
          onChange={(next) => set('memory_interval', next)}
          placeholder="默认 50，范围 1–1000"
        />
        <div className="ui-field" />
      </div>

      <ToolSelection
        value={form.enabled_tools}
        tools={tools}
        onChange={(next) => set('enabled_tools', next)}
      />

      <AccessLists
        value={form}
        snapshot={snapshot}
        onChange={(patch) => setForm((previous) => ({ ...previous, ...patch }))}
      />

      {saveError ? (
        <div className="form-error">
          <CircleAlert size={15} />
          {saveError}
        </div>
      ) : null}

      <ModalFooter onClose={onClose} onSave={submit} busy={saving} />
    </Modal>
  );
}
