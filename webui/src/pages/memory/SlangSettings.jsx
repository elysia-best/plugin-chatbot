import { CircleAlert } from 'lucide-react';
import Button from '../../components/ui/Button.jsx';
import { CheckRow, Field, SelectField } from '../../components/ui/Field.jsx';
import { providerLabel } from '../../lib/format.js';

/** 黑话学习与自动审核配置块。 */
export default function SlangSettings({
  settings,
  providers = [],
  reviewDraft,
  onDraftChange,
  onToggleEnabled,
  onSave,
}) {
  return (
    <div className="memory-page__settings">
      <div className="memory-page__settings-row">
        <CheckRow
          label="自动学习黑话"
          checked={settings.enabled}
          onChange={onToggleEnabled}
        />
        <span className="text-faint">
          每 {settings.min_messages} 条群消息触发一次，冷却 {settings.cooldown_seconds} 秒
        </span>
      </div>

      <div className="memory-page__review">
        <SelectField
          label="自动审核接口"
          value={reviewDraft.review_provider_id}
          options={['', ...providers.map((provider) => provider.id)]}
          labels={['不审核（新词保持待审核）', ...providers.map(providerLabel)]}
          onChange={(value) => onDraftChange({ ...reviewDraft, review_provider_id: value })}
        />
        <Field
          label="审核模型（可选）"
          value={reviewDraft.review_model}
          onChange={(value) => onDraftChange({ ...reviewDraft, review_model: value })}
          placeholder="留空使用接口默认模型"
        />
        <Button variant="soft" size="sm" onClick={onSave}>
          保存审核配置
        </Button>
        {!settings.review_configured ? (
          <span className="memory-page__warn">
            <CircleAlert size={14} />
            未配置审核接口，新词将保持待审核
          </span>
        ) : null}
      </div>
      <p className="inline-note">
        研究完成后自动判定：有效解释放行，无效词条直接删除；接口故障时保持待审核。
      </p>
    </div>
  );
}
