import { Field } from '../../components/ui/Field.jsx';
import Modal, { ModalFooter } from '../../components/ui/Modal.jsx';

/** 记忆条目编辑浮层：全局 / Bot / 待审核草稿共用同一套字段。 */
export default function MemoryEntryEditor({ title, editor, onChange, onClose, onSave, busy = false }) {
  return (
    <Modal title={title} kicker="MEMORY ENTRY" size="lg" onClose={onClose}>
      <div className="form-grid form-grid--two">
        <Field
          label="稳定名称"
          value={editor.name}
          onChange={(value) => onChange({ name: value })}
          placeholder="例如 project-guidelines"
        />
        <Field label="标题" value={editor.title} onChange={(value) => onChange({ title: value })} />
        <Field label="类型" value={editor.type} onChange={(value) => onChange({ type: value })} />
        <Field
          label="说明"
          value={editor.description}
          onChange={(value) => onChange({ description: value })}
        />
        <Field
          label="记忆内容"
          wide
          type="textarea"
          rows={10}
          value={editor.content}
          onChange={(value) => onChange({ content: value })}
        />
      </div>
      <ModalFooter onClose={onClose} onSave={onSave} busy={busy} />
    </Modal>
  );
}
