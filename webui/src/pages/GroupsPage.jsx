import { useState } from 'react';
import { MessageSquareText, Pencil, Plus, Trash2, UsersRound } from 'lucide-react';
import Button from '../components/ui/Button.jsx';
import Card from '../components/ui/Card.jsx';
import DataTable, { Cell, DataRow, IdentityCell } from '../components/ui/DataTable.jsx';
import EmptyState from '../components/ui/EmptyState.jsx';
import PageHeader from '../components/ui/PageHeader.jsx';
import { StatusBadge } from '../components/ui/Badge.jsx';
import { useConfirm } from '../components/feedback/ConfirmProvider.jsx';
import { useToast } from '../components/feedback/ToastProvider.jsx';
import { api } from '../lib/api.js';
import { modelId, providerLabel } from '../lib/format.js';
import GroupEditor from './groups/GroupEditor.jsx';

export default function GroupsPage({ token, snapshot, tools, onRefresh }) {
  const [editor, setEditor] = useState(null);
  const [busyId, setBusyId] = useState('');
  const groups = snapshot.groups || [];
  const accounts = snapshot.accounts || [];
  const providers = snapshot.interfaces?.providers || [];
  const confirm = useConfirm();
  const toast = useToast();

  async function save(body) {
    await api(token, editor.id ? `/groups/${editor.id}` : '/groups', editor.id ? 'PUT' : 'POST', body);
    await onRefresh();
    setEditor(null);
    toast.success('群聊策略已保存');
  }

  async function remove(group) {
    const ok = await confirm({
      title: '删除群聊策略',
      message: `确认删除「${group.name || group.group_id}」的群聊策略？之后该群会跟随账号默认配置。`,
      confirmLabel: '删除策略',
      tone: 'danger',
    });
    if (!ok) return;
    setBusyId(group.id);
    try {
      await api(token, `/groups/${group.id}`, 'DELETE');
      await onRefresh();
      toast.success('群聊策略已删除');
    } catch (err) {
      toast.error(err.message);
    } finally {
      setBusyId('');
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        kicker="GROUP POLICIES"
        title="群聊策略"
        description="群聊提示词会完整覆盖账号人格；回复概率 0~1，未命中的消息会暂存并在下次回复时带上时间戳交给模型。"
        action="添加策略"
        actionIcon={Plus}
        onAction={() => setEditor({})}
      />

      <Card bare>
        <div className="table-toolbar">
          <div className="table-toolbar__title">
            <UsersRound size={17} />
            <span>{groups.length} 个群聊策略</span>
          </div>
          <span className="text-faint">群名称优先来自 adapter</span>
        </div>

        {groups.length ? (
          <DataTable
            layout="minmax(230px, 1.4fr) minmax(120px, .8fr) minmax(120px, .8fr) 78px 88px 112px 96px"
            minWidth={1040}
          >
            <div className="ui-table__head">
              <span>群聊</span>
              <span>供应商</span>
              <span>模型</span>
              <span>工具</span>
              <span>回复概率</span>
              <span>状态</span>
              <span className="ui-table__head-end">操作</span>
            </div>
            {groups.map((group, index) => {
              const provider = providers.find((item) => item.id === group.provider_id);
              return (
                <DataRow key={group.id} index={index}>
                  <IdentityCell
                    icon={MessageSquareText}
                    tone="mint"
                    title={group.name || group.group_id}
                    subtitle={`${group.platform} / ${group.bot_id} · ${group.group_id}`}
                  />
                  <Cell>{providerLabel(provider) || '跟随账号'}</Cell>
                  <Cell>{modelId(group.model) || modelId(provider?.model) || '账号默认'}</Cell>
                  <Cell>{group.enabled_tools?.length || '继承默认'}</Cell>
                  <Cell>{group.reply_probability ?? 1}</Cell>
                  <Cell>
                    <StatusBadge enabled={group.enabled !== false} />
                  </Cell>
                  <div className="ui-table__actions">
                    <Button
                      variant="icon"
                      size="sm"
                      icon={Pencil}
                      title="编辑策略"
                      aria-label="编辑策略"
                      onClick={() => setEditor(group)}
                    />
                    <Button
                      variant="icon-danger"
                      size="sm"
                      icon={Trash2}
                      title="删除策略"
                      aria-label="删除策略"
                      loading={busyId === group.id}
                      onClick={() => remove(group)}
                    />
                  </div>
                </DataRow>
              );
            })}
          </DataTable>
        ) : (
          <EmptyState
            title="还没有群聊策略"
            detail="先添加账号，再为账号绑定群聊 ID。"
            action="添加策略"
            actionIcon={Plus}
            onAction={() => setEditor({})}
          />
        )}
      </Card>

      {editor ? (
        <GroupEditor
          value={editor}
          accounts={accounts}
          providers={providers}
          tools={tools}
          onClose={() => setEditor(null)}
          onSave={save}
        />
      ) : null}
    </div>
  );
}
