import { useCallback, useEffect, useState } from 'react';
import { CircleAlert, Pencil, Plus, Trash2, Wrench } from 'lucide-react';
import Button from '../../components/ui/Button.jsx';
import DataTable, { Cell, DataRow, IdentityCell } from '../../components/ui/DataTable.jsx';
import EmptyState from '../../components/ui/EmptyState.jsx';
import { SkeletonRows } from '../../components/ui/Skeleton.jsx';
import { StatePill } from '../../components/ui/Badge.jsx';
import { useConfirm } from '../../components/feedback/ConfirmProvider.jsx';
import { useToast } from '../../components/feedback/ToastProvider.jsx';
import { api } from '../../lib/api.js';
import CustomToolEditor, { MAX_TOOLS, SCOPE_LABELS } from './CustomToolEditor.jsx';
import './CustomToolsPanel.css';

export default function CustomToolsPanel({ token, groups = [], onRefresh }) {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState('');
  const [busyId, setBusyId] = useState('');
  const { confirm } = useConfirm();
  const toast = useToast();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setRows(await api(token, '/custom-tools'));
      setError('');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  async function saved() {
    setEditing('');
    await load();
    if (onRefresh) await onRefresh();
    toast.success('自定义 Tool 已保存');
  }

  async function toggle(row) {
    setBusyId(row.id);
    setError('');
    try {
      await api(token, `/custom-tools/${row.id}`, 'PUT', { enabled: !row.enabled });
      await load();
      toast.success(row.enabled ? '已停用该工具' : '已启用该工具');
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId('');
    }
  }

  async function remove(row) {
    const ok = await confirm({
      title: '删除自定义 Tool',
      message: `删除 ${row.name}？脚本文件会一并删除，且不可恢复。`,
      confirmLabel: '删除工具',
      tone: 'danger',
    });
    if (!ok) return;
    setBusyId(row.id);
    setError('');
    try {
      await api(token, `/custom-tools/${row.id}`, 'DELETE');
      await load();
      if (onRefresh) await onRefresh();
      toast.success('自定义 Tool 已删除');
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId('');
    }
  }

  return (
    <div className="custom-tools">
      <div className="table-toolbar">
        <div className="table-toolbar__title">
          <Wrench size={17} />
          <span>自定义 Tool</span>
          <span className="text-faint">
            {rows.length}/{MAX_TOOLS}，只能在这里增改
          </span>
        </div>
        <Button
          variant="primary"
          size="sm"
          icon={Plus}
          disabled={rows.length >= MAX_TOOLS}
          onClick={() => setEditing('new')}
        >
          新增自定义 Tool
        </Button>
      </div>

      {error ? (
        <div className="form-error custom-tools__error">
          <CircleAlert size={15} />
          {error}
        </div>
      ) : null}

      {loading ? (
        <SkeletonRows rows={4} />
      ) : rows.length ? (
        <DataTable layout="minmax(240px, 1.5fr) 200px 250px" minWidth={760}>
          <div className="ui-table__head">
            <span>工具</span>
            <span>范围 / 超时</span>
            <span className="ui-table__head-end">操作</span>
          </div>
          {rows.map((row, index) => (
            <DataRow key={row.id} index={index}>
              <IdentityCell
                icon={Wrench}
                tone="amber"
                title={row.name}
                subtitle={row.description || '尚未填写描述'}
              />
              <Cell>
                {SCOPE_LABELS[row.scope] || row.scope} · {row.timeout}s
              </Cell>
              <div className="ui-table__actions">
                {row.status === 'invalid' ? (
                  <StatePill tone="danger">文件异常</StatePill>
                ) : null}
                <Button
                  variant="soft"
                  size="sm"
                  loading={busyId === row.id}
                  onClick={() => toggle(row)}
                >
                  {row.enabled ? '停用' : '启用'}
                </Button>
                <Button
                  variant="icon"
                  size="sm"
                  icon={Pencil}
                  title="编辑"
                  aria-label="编辑"
                  onClick={() => setEditing(row.id)}
                />
                <Button
                  variant="icon-danger"
                  size="sm"
                  icon={Trash2}
                  title="删除"
                  aria-label="删除"
                  onClick={() => remove(row)}
                />
              </div>
            </DataRow>
          ))}
        </DataTable>
      ) : (
        <EmptyState
          icon={Wrench}
          title="还没有自定义 Tool"
          detail="写一段 Python 脚本，让模型能在工作区执行命令并读取输出。"
          action="新增自定义 Tool"
          actionIcon={Plus}
          onAction={() => setEditing('new')}
        />
      )}

      {editing ? (
        <CustomToolEditor
          token={token}
          groups={groups}
          toolId={editing === 'new' ? '' : editing}
          onClose={() => setEditing('')}
          onSaved={saved}
        />
      ) : null}
    </div>
  );
}
