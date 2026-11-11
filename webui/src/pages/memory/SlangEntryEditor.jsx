import { CircleAlert } from 'lucide-react';
import { Field } from '../../components/ui/Field.jsx';
import Modal, { ModalFooter } from '../../components/ui/Modal.jsx';

/** 黑话词条编辑浮层。 */
export default function SlangEntryEditor({ editor, onChange, onClose, onSave, busy = false, error = '' }) {
  return (
    <Modal
      title={editor.id ? '编辑黑话词条' : '新增黑话词条'}
      kicker="SLANG ENTRY"
      onClose={onClose}
    >
      <div className="form-grid form-grid--two">
        <Field label="黑话" value={editor.term} onChange={(value) => onChange({ term: value })} />
        <Field
          label="含义"
          wide
          type="textarea"
          rows={4}
          value={editor.meaning}
          onChange={(value) => onChange({ meaning: value })}
        />
      </div>
      {error ? (
        <div className="form-error">
          <CircleAlert size={15} />
          {error}
        </div>
      ) : null}
      <ModalFooter onClose={onClose} onSave={onSave} busy={busy} />
    </Modal>
  );
}
