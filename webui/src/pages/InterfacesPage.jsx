import { useState } from 'react';
import {
  Pencil,
  Plug,
  Plus,
  RefreshCw,
  ScrollText,
  Server,
  Sparkles,
  Trash2,
  Wrench,
} from 'lucide-react';
import Button from '../components/ui/Button.jsx';
import Card from '../components/ui/Card.jsx';
import DataTable, { Cell, DataRow, IdentityCell } from '../components/ui/DataTable.jsx';
import EmptyState from '../components/ui/EmptyState.jsx';
import PageHeader from '../components/ui/PageHeader.jsx';
import Tabs from '../components/ui/Tabs.jsx';
import { useConfirm } from '../components/feedback/ConfirmProvider.jsx';
import { useToast } from '../components/feedback/ToastProvider.jsx';
import { api } from '../lib/api.js';
import CapabilityEditor from './interfaces/CapabilityEditor.jsx';
import OpenWebSearchCard from './interfaces/OpenWebSearchCard.jsx';
import CustomToolsPanel from './interfaces/CustomToolsPanel.jsx';
import './InterfacesPage.css';

const TABS = [
  { id: 'providers', label: 'AI 接口', icon: Plug },
  { id: 'tools', label: 'Tools', icon: Wrench },
  { id: 'custom_tools', label: '自定义 Tool', icon: Wrench },
  { id: 'skills', label: 'Skill', icon: Sparkles },
  { id: 'mcps', label: 'MCP', icon: Server },
  { id: 'rules', label: 'Rules', icon: ScrollText },
];

export default function InterfacesPage({ token, snapshot, tools, onRefresh }) {
  const [tab, setTab] = useState('providers');
  const [editor, setEditor] = useState(null);
  const [busyId, setBusyId] = useState('');
  const confirm = useConfirm();
  const toast = useToast();

  const rows = tab === 'tools' ? tools : tab === 'custom_tools' ? [] : snapshot.interfaces?.[tab] || [];
  const readOnly = tab === 'tools' || tab === 'custom_tools';

  async function save(body) {
    await api(
      token,
      editor.id ? `/interfaces/${tab}/${editor.id}` : `/interfaces/${tab}`,
      editor.id ? 'PUT' : 'POST',
      body,
    );
    await onRefresh();
    setEditor(null);
    toast.success('能力已保存');
  }

  async function remove(row) {
    const ok = await confirm({
      title: '删除能力',
      message: `确认删除「${row.name || row.id}」？引用它的账号或群聊会回落到默认配置。`,
      confirmLabel: '删除',
      tone: 'danger',
    });
    if (!ok) return;
    setBusyId(row.id);
    try {
      await api(token, `/interfaces/${tab}/${row.id}`, 'DELETE');
      await onRefresh();
      toast.success('能力已删除');
    } catch (err) {
      toast.error(err.message);
    } finally {
      setBusyId('');
    }
  }

  async function discover(row) {
    setBusyId(row.id);
    try {
      await api(token, `/interfaces/providers/${row.id}/models`, 'POST');
      await onRefresh();
      toast.success('模型列表已更新');
    } catch (err) {
      toast.error(err.message);
    } finally {
      setBusyId('');
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        kicker="INTERFACE CAPABILITIES"
        title="接口能力"
        description="管理 AI 接口、实际可用 Tools，以及群聊策略可以勾选的能力目录。"
        action={readOnly ? null : '新增能力'}
        actionIcon={Plus}
        onAction={() => setEditor({})}
      />

      <Card bare>
        <div className="interfaces-page__tabs">
          <Tabs items={TABS} value={tab} onChange={setTab} />
        </div>

        {tab === 'mcps' ? (
          <div className="interfaces-page__mcp">
            <OpenWebSearchCard token={token} />
          </div>
        ) : null}

        {tab === 'custom_tools' ? (
          <CustomToolsPanel token={token} groups={snapshot.groups || []} onRefresh={onRefresh} />
        ) : rows.length ? (
          <DataTable layout="minmax(260px, 1.6fr) 170px 200px" minWidth={720}>
            <div className="ui-table__head">
              <span>能力</span>
              <span>{tab === 'providers' ? '模型' : tab === 'tools' ? '来源' : '类型'}</span>
              <span className="ui-table__head-end">操作</span>
            </div>
            {rows.map((row, index) => (
              <DataRow key={row.id || row.name} index={index}>
                <IdentityCell
                  icon={tab === 'tools' ? Wrench : Plug}
                  tone={tab === 'tools' ? 'mint' : 'indigo'}
                  title={row.name || row.id}
                  subtitle={
                    row.description || row.base_url || row.url || row.content || row.category || '尚未填写描述'
                  }
                />
                <Cell>
                  {tab === 'providers'
                    ? `${row.models?.length || 0} 个已发现`
                    : tab === 'tools'
                      ? row.source
                      : tab.toUpperCase()}
                </Cell>
                <div className="ui-table__actions">
                  {tab === 'providers' ? (
                    <Button
                      variant="soft"
                      size="sm"
                      icon={RefreshCw}
                      loading={busyId === row.id}
                      onClick={() => discover(row)}
                    >
                      拉取模型
                    </Button>
                  ) : null}
                  {tab !== 'tools' ? (
                    <>
                      <Button
                        variant="icon"
                        size="sm"
                        icon={Pencil}
                        title="编辑"
                        aria-label="编辑"
                        onClick={() => setEditor(row)}
                      />
                      <Button
                        variant="icon-danger"
                        size="sm"
                        icon={Trash2}
                        title="删除"
                        aria-label="删除"
                        loading={busyId === row.id}
                        onClick={() => remove(row)}
                      />
                    </>
                  ) : null}
                </div>
              </DataRow>
            ))}
          </DataTable>
        ) : (
          <EmptyState
            title={tab === 'tools' ? '暂无可用工具' : '还没有接口能力'}
            detail={
              tab === 'tools'
                ? '工具会根据当前桥接模式和 MCP 连接显示。'
                : '新增 AI 接口后可以在窗口中拉取模型。'
            }
            action={tab === 'tools' ? null : '新增能力'}
            actionIcon={Plus}
            onAction={() => setEditor({})}
          />
        )}
      </Card>

      {editor ? (
        <CapabilityEditor
          token={token}
          kind={tab}
          value={editor}
          onClose={() => setEditor(null)}
          onSave={save}
        />
      ) : null}
    </div>
  );
}
