import { useState } from 'react';
import { Bot, MessageSquareText, Pencil, Plus, Trash2 } from 'lucide-react';
import Button from '../components/ui/Button.jsx';
import Card from '../components/ui/Card.jsx';
import DataTable, { Cell, DataRow, IdentityCell } from '../components/ui/DataTable.jsx';
import EmptyState from '../components/ui/EmptyState.jsx';
import PageHeader from '../components/ui/PageHeader.jsx';
import { StatusBadge } from '../components/ui/Badge.jsx';
import { useConfirm } from '../components/feedback/ConfirmProvider.jsx';
import { useToast } from '../components/feedback/ToastProvider.jsx';
import { api } from '../lib/api.js';
import { providerLabel } from '../lib/format.js';
import AccountEditor from './accounts/AccountEditor.jsx';
import './AccountsPage.css';

export default function AccountsPage({ token, snapshot, roles, tools, onRefresh }) {
  const [editor, setEditor] = useState(null);
  const [busyId, setBusyId] = useState('');
  const accounts = snapshot.accounts || [];
  const providers = snapshot.interfaces?.providers || [];
  const confirm = useConfirm();
  const toast = useToast();

  async function save(body) {
    const { admins = [], whitelist = [], blacklist = [], ...accountBody } = body;
    const saved = await api(
      token,
      editor.id ? `/accounts/${editor.id}` : '/accounts',
      editor.id ? 'PUT' : 'POST',
      accountBody,
    );
    if (!editor.id) setEditor((current) => ({ ...current, id: saved.id }));
    await api(token, `/accounts/${saved.id}/access`, 'PUT', { admins, whitelist, blacklist });
    await onRefresh();
    setEditor(null);
    toast.success('账号设置已保存');
  }

  async function remove(account) {
    const ok = await confirm({
      title: '删除平台账号',
      message: `确认删除「${account.name || account.bot_id}」？该账号的群聊策略与访问名单会一并失效。`,
      confirmLabel: '删除账号',
      tone: 'danger',
    });
    if (!ok) return;
    setBusyId(account.id);
    try {
      await api(token, `/accounts/${account.id}`, 'DELETE');
      await onRefresh();
      toast.success('账号已删除');
    } catch (err) {
      toast.error(err.message);
    } finally {
      setBusyId('');
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        kicker="PLATFORM ACCOUNTS"
        title="平台账号"
        description="每个 Bot 都拥有独立的接口、人格和工具默认值。名称来自 adapter 时优先展示昵称。"
        action="新增账号"
        actionIcon={Plus}
        onAction={() => setEditor({})}
      />

      <Card bare>
        <div className="table-toolbar">
          <div className="table-toolbar__title">
            <Bot size={17} />
            <span>{accounts.length} 个账号</span>
          </div>
          <span className="text-faint">ID 保留用于精确定位</span>
        </div>

        {accounts.length ? (
          <DataTable
            layout="minmax(240px, 1.5fr) minmax(150px, 1fr) 110px 120px 96px"
            minWidth={820}
          >
            <div className="ui-table__head">
              <span>账号</span>
              <span>AI 接口</span>
              <span>群聊</span>
              <span>状态</span>
              <span className="ui-table__head-end">操作</span>
            </div>
            {accounts.map((account, index) => {
              const provider = providers.find((item) => item.id === account.provider_id);
              const groupCount = (snapshot.groups || []).filter(
                (group) =>
                  group.platform === account.platform && group.bot_id === account.bot_id,
              ).length;
              return (
                <DataRow key={account.id} index={index}>
                  <IdentityCell
                    icon={Bot}
                    title={account.name || account.bot_id}
                    subtitle={`${account.platform} · ${account.bot_id}`}
                  />
                  <Cell>{providerLabel(provider) || '未选择接口'}</Cell>
                  <Cell>
                    <span className="accounts-page__groups">
                      <MessageSquareText size={13} />
                      {groupCount} 个策略
                    </span>
                  </Cell>
                  <Cell>
                    <StatusBadge enabled={account.enabled !== false} />
                  </Cell>
                  <div className="ui-table__actions">
                    <Button
                      variant="icon"
                      size="sm"
                      icon={Pencil}
                      title="编辑账号"
                      aria-label="编辑账号"
                      onClick={() => setEditor(account)}
                    />
                    <Button
                      variant="icon-danger"
                      size="sm"
                      icon={Trash2}
                      title="删除账号"
                      aria-label="删除账号"
                      loading={busyId === account.id}
                      onClick={() => remove(account)}
                    />
                  </div>
                </DataRow>
              );
            })}
          </DataTable>
        ) : (
          <EmptyState
            title="还没有平台账号"
            detail="可以等待消息自动发现 Bot，也可以立即新增一个账号。"
            action="新增账号"
            actionIcon={Plus}
            onAction={() => setEditor({})}
          />
        )}
      </Card>

      {editor ? (
        <AccountEditor
          value={editor}
          roles={roles.roles || []}
          tools={tools}
          providers={providers}
          snapshot={snapshot}
          onClose={() => setEditor(null)}
          onSave={save}
        />
      ) : null}
    </div>
  );
}
