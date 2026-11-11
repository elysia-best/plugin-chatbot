import { useState } from 'react';
import { Copy, Pencil, Plus, Sparkles, Star, Trash2 } from 'lucide-react';
import Button from '../components/ui/Button.jsx';
import Card from '../components/ui/Card.jsx';
import DataTable, { Cell, DataRow, IdentityCell } from '../components/ui/DataTable.jsx';
import EmptyState from '../components/ui/EmptyState.jsx';
import Modal, { ModalFooter } from '../components/ui/Modal.jsx';
import PageHeader from '../components/ui/PageHeader.jsx';
import { Field } from '../components/ui/Field.jsx';
import { StatePill } from '../components/ui/Badge.jsx';
import { useConfirm } from '../components/feedback/ConfirmProvider.jsx';
import { useToast } from '../components/feedback/ToastProvider.jsx';
import { api } from '../lib/api.js';

const MAX_CONTENT = 24000;

export default function PersonasPage({ token, roles, onRolesChange }) {
  const [editor, setEditor] = useState(null);
  const [busy, setBusy] = useState(false);
  const { confirm, prompt: promptDialog } = useConfirm();
  const toast = useToast();
  const rows = roles.roles || [];

  async function reload() {
    onRolesChange(await api(token, '/roles'));
  }

  async function save() {
    if (!editor?.name?.trim()) {
      toast.error('请填写模板名称');
      return;
    }
    setBusy(true);
    try {
      await api(
        token,
        editor.original ? `/roles/${encodeURIComponent(editor.original)}` : '/roles',
        editor.original ? 'PUT' : 'POST',
        editor.original ? { value: editor.content } : { name: editor.name.trim(), content: editor.content },
      );
      await reload();
      setEditor(null);
      toast.success(editor.original ? '人格模板已更新' : '人格模板已创建');
    } catch (err) {
      toast.error(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function activate(name) {
    try {
      await api(token, '/active-role', 'PUT', { name: name || null });
      await reload();
      toast.success(name ? `已将「${name}」设为默认人格` : '已取消默认人格');
    } catch (err) {
      toast.error(err.message);
    }
  }

  async function remove(name) {
    const ok = await confirm({
      title: '删除人格模板',
      message: `确认删除人格模板「${name}」？引用该模板的账号将回落到全局默认。`,
      confirmLabel: '删除模板',
      tone: 'danger',
    });
    if (!ok) return;
    try {
      await api(token, `/roles/${encodeURIComponent(name)}`, 'DELETE');
      await reload();
      toast.success('人格模板已删除');
    } catch (err) {
      toast.error(err.message);
    }
  }

  async function copy(name) {
    const next = await promptDialog({
      title: '复制人格模板',
      message: '为新模板命名，内容会完整复制一份。',
      confirmLabel: '复制',
      defaultValue: `${name}-副本`,
      placeholder: '模板名称',
    });
    if (!next) return;
    try {
      await api(token, `/roles/${encodeURIComponent(name)}/copy`, 'POST', { name: next });
      await reload();
      toast.success('已复制模板');
    } catch (err) {
      toast.error(err.message);
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        kicker="PERSONA WORKBENCH"
        title="人格提示"
        description="创建可复用的人格模板，并在平台账号中选择模板，再追加账号专属提示。"
        action="新建模板"
        actionIcon={Plus}
        onAction={() => setEditor({ name: '', content: '' })}
      >
        <StatePill tone="blossom">默认人格：{roles.active || '未设置'}</StatePill>
      </PageHeader>

      <Card bare>
        <div className="table-toolbar">
          <div className="table-toolbar__title">
            <Sparkles size={17} />
            <span>{rows.length} 个模板</span>
          </div>
          <span className="text-faint">人格会注入到系统提示中</span>
        </div>

        {rows.length ? (
          <DataTable layout="minmax(260px, 1.6fr) 140px 210px" minWidth={720}>
            <div className="ui-table__head">
              <span>模板</span>
              <span>状态</span>
              <span className="ui-table__head-end">操作</span>
            </div>
            {rows.map((role, index) => {
              const active = roles.active === role.name;
              return (
                <DataRow key={role.name} index={index}>
                  <IdentityCell
                    icon={Sparkles}
                    tone={active ? 'blossom' : 'indigo'}
                    title={role.name}
                    subtitle={`${role.chars} 字 · ${role.sections?.length || 0} 个章节`}
                  />
                  <Cell>
                    {active ? (
                      <StatePill tone="blossom">
                        <Star size={12} />
                        全局默认
                      </StatePill>
                    ) : (
                      <StatePill>可选模板</StatePill>
                    )}
                  </Cell>
                  <div className="ui-table__actions">
                    <Button variant="soft" size="sm" onClick={() => activate(active ? null : role.name)}>
                      {active ? '取消默认' : '设为默认'}
                    </Button>
                    <Button
                      variant="icon"
                      size="sm"
                      icon={Copy}
                      title="复制"
                      aria-label="复制模板"
                      onClick={() => copy(role.name)}
                    />
                    <Button
                      variant="icon"
                      size="sm"
                      icon={Pencil}
                      title="编辑"
                      aria-label="编辑模板"
                      onClick={() =>
                        setEditor({ name: role.name, original: role.name, content: role.content })
                      }
                    />
                    <Button
                      variant="icon-danger"
                      size="sm"
                      icon={Trash2}
                      title="删除"
                      aria-label="删除模板"
                      onClick={() => remove(role.name)}
                    />
                  </div>
                </DataRow>
              );
            })}
          </DataTable>
        ) : (
          <EmptyState
            title="还没有人格模板"
            detail="创建第一个模板后，就能在平台账号中直接选择。"
            action="新建模板"
            actionIcon={Plus}
            onAction={() => setEditor({ name: '', content: '' })}
          />
        )}
      </Card>

      {editor ? (
        <Modal
          title={editor.original ? '编辑人格模板' : '新建人格模板'}
          kicker="PERSONA TEMPLATE"
          size="lg"
          onClose={() => setEditor(null)}
        >
          <div className="form-grid">
            <Field
              label="模板名称"
              value={editor.name}
              onChange={(name) => setEditor({ ...editor, name })}
              placeholder="例如：值班助手"
            />
            <Field
              label={`人格内容（${(editor.content || '').length} / ${MAX_CONTENT}）`}
              wide
              type="textarea"
              rows={14}
              value={editor.content}
              onChange={(content) => setEditor({ ...editor, content })}
              placeholder="写下说话风格、边界和角色规则。"
            />
          </div>
          <ModalFooter onClose={() => setEditor(null)} onSave={save} busy={busy} />
        </Modal>
      ) : null}
    </div>
  );
}
