import { useEffect, useState } from 'react';
import {
  BookOpen,
  Check,
  MessageSquareText,
  Pencil,
  Plus,
  Trash2,
} from 'lucide-react';
import Button from '../components/ui/Button.jsx';
import Card from '../components/ui/Card.jsx';
import DataTable, { Cell, DataRow, IdentityCell } from '../components/ui/DataTable.jsx';
import EmptyState from '../components/ui/EmptyState.jsx';
import PageHeader from '../components/ui/PageHeader.jsx';
import Tabs from '../components/ui/Tabs.jsx';
import { CheckRow, Field, SelectField } from '../components/ui/Field.jsx';
import { SkeletonRows } from '../components/ui/Skeleton.jsx';
import { useConfirm } from '../components/feedback/ConfirmProvider.jsx';
import { useToast } from '../components/feedback/ToastProvider.jsx';
import { api } from '../lib/api.js';
import { formatTime, memorySlug } from '../lib/format.js';
import MemoryEntryEditor from './memory/MemoryEntryEditor.jsx';
import SlangEntryEditor from './memory/SlangEntryEditor.jsx';
import SlangSettings from './memory/SlangSettings.jsx';
import './MemoryPage.css';

export default function MemoryPage({ token, snapshot, onRefresh }) {
  const accounts = snapshot?.accounts || [];
  const providers = snapshot?.interfaces?.providers || [];

  const [tab, setTab] = useState('global');
  const [accountId, setAccountId] = useState(accounts[0]?.id || '');
  const [memories, setMemories] = useState([]);
  const [index, setIndex] = useState('');
  const [queue, setQueue] = useState([]);
  const [slang, setSlang] = useState([]);
  const [settings, setSettings] = useState({
    enabled: true,
    min_messages: 10,
    cooldown_seconds: 300,
    review_provider_id: '',
    review_model: '',
    review_configured: false,
  });
  const [editor, setEditor] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [botSettings, setBotSettings] = useState({ enabled: true, interval: 50 });
  const [savingSettings, setSavingSettings] = useState(false);
  const [reviewDraft, setReviewDraft] = useState({ review_provider_id: '', review_model: '' });
  const [busy, setBusy] = useState(false);
  const { confirm } = useConfirm();
  const toast = useToast();

  const account = accounts.find((row) => row.id === accountId);
  const memoryBase = tab === 'bot' && account ? `/accounts/${account.id}/memories` : '/memories';

  async function reload() {
    setLoading(true);
    try {
      const [memoryRows, memoryIndex, queueRows, slangRows, slangSettings] = await Promise.all([
        tab === 'bot' && account ? api(token, memoryBase) : api(token, '/memories'),
        tab === 'global' ? api(token, '/memories/index') : Promise.resolve({ content: '' }),
        api(token, '/memory-queue'),
        api(token, '/slang'),
        api(token, '/slang/settings'),
      ]);
      setMemories(memoryRows);
      setIndex(memoryIndex.content || '');
      setQueue(queueRows);
      setSlang(slangRows);
      setSettings(slangSettings);
      setError('');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!accountId && accounts[0]) setAccountId(accounts[0].id);
  }, [accounts, accountId]);

  useEffect(() => {
    setBotSettings({
      enabled: account?.memory_enabled !== false,
      interval: account?.memory_interval || 50,
    });
  }, [accountId, account?.memory_enabled, account?.memory_interval]);

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, tab, accountId]);

  useEffect(() => {
    setReviewDraft({
      review_provider_id: settings.review_provider_id || '',
      review_model: settings.review_model || '',
    });
  }, [settings.review_provider_id, settings.review_model]);

  async function saveBotSettings() {
    if (!account) return;
    setSavingSettings(true);
    try {
      await api(token, `/accounts/${account.id}`, 'PUT', {
        memory_enabled: botSettings.enabled,
        memory_interval: Number(botSettings.interval) || 50,
      });
      await onRefresh();
      setError('');
      toast.success('Bot 记忆设置已保存');
    } catch (err) {
      setError(err.message);
    } finally {
      setSavingSettings(false);
    }
  }

  function newMemory() {
    setEditor({ name: '', title: '', description: '', type: 'project', content: '' });
  }

  async function saveMemory() {
    setBusy(true);
    try {
      const body = {
        name: editor.name.trim() || memorySlug(editor.title),
        title: editor.title.trim(),
        description: editor.description.trim(),
        type: editor.type || 'project',
        content: editor.content.trim(),
      };
      if (editor.queueId) await api(token, `/memory-queue/${editor.queueId}`, 'PATCH', body);
      else
        await api(
          token,
          editor.original ? `${memoryBase}/${encodeURIComponent(editor.original)}` : memoryBase,
          editor.original ? 'PUT' : 'POST',
          body,
        );
      await reload();
      setEditor(null);
      toast.success('记忆已保存');
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function openMemory(row) {
    try {
      setEditor({ ...(await api(token, `${memoryBase}/${encodeURIComponent(row.name)}`)), original: row.name });
    } catch (err) {
      setError(err.message);
    }
  }

  async function removeMemory(name) {
    const ok = await confirm({
      title: '删除记忆',
      message: `确认删除记忆「${name}」？该条目会从 Memory 索引中移除。`,
      confirmLabel: '删除记忆',
      tone: 'danger',
    });
    if (!ok) return;
    try {
      await api(token, `${memoryBase}/${encodeURIComponent(name)}`, 'DELETE');
      await reload();
      toast.success('记忆已删除');
    } catch (err) {
      setError(err.message);
    }
  }

  async function approveCandidate(row) {
    try {
      await api(token, `/memory-queue/${row.id}/approve`, 'POST', {
        name: row.name || memorySlug(row.title),
      });
      await reload();
      toast.success('记忆草稿已通过');
    } catch (err) {
      setError(err.message);
    }
  }

  async function removeCandidate(id) {
    const ok = await confirm({
      title: '删除待审核记忆',
      message: '确认删除这条待审核记忆？删除后不会写入 Memory。',
      confirmLabel: '删除',
      tone: 'danger',
    });
    if (!ok) return;
    try {
      await api(token, `/memory-queue/${id}`, 'DELETE');
      await reload();
      toast.success('草稿已删除');
    } catch (err) {
      setError(err.message);
    }
  }

  async function saveSlang() {
    setBusy(true);
    try {
      const body = { term: editor.term.trim(), meaning: editor.meaning || '' };
      if (editor.id) await api(token, `/slang/${editor.id}`, 'PATCH', { ...body, status: editor.status });
      else await api(token, '/slang', 'POST', body);
      await reload();
      setEditor(null);
      toast.success('黑话词条已保存');
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function updateSettings(next) {
    try {
      const saved = await api(token, '/slang/settings', 'PUT', next);
      setSettings(saved);
      setError('');
    } catch (err) {
      setError(err.message);
    }
  }

  async function saveReviewSettings() {
    await updateSettings({ ...settings, ...reviewDraft });
    toast.success('自动审核配置已保存');
  }

  async function reviewSlang(row) {
    try {
      await api(token, `/slang/${row.id}`, 'PATCH', {
        status: row.status === 'confirmed' ? 'candidate' : 'confirmed',
      });
      await reload();
    } catch (err) {
      setError(err.message);
    }
  }

  async function removeSlang(id) {
    const ok = await confirm({
      title: '删除黑话词条',
      message: '确认删除这个黑话词条？删除后不会再注入系统提示。',
      confirmLabel: '删除',
      tone: 'danger',
    });
    if (!ok) return;
    try {
      await api(token, `/slang/${id}`, 'DELETE');
      await reload();
      toast.success('词条已删除');
    } catch (err) {
      setError(err.message);
    }
  }

  const memoryTabs = [
    { id: 'global', label: '全局 Memory', icon: BookOpen },
    { id: 'bot', label: 'Bot Memory', icon: BookOpen },
    { id: 'review', label: '待审核', icon: Check, count: queue.length },
    { id: 'slang', label: '黑话词库', icon: MessageSquareText },
  ];

  const showMemoryEditor = editor && ['global', 'bot'].includes(tab) && !editor.queueId;
  const canCreate = tab === 'global' || (tab === 'bot' && Boolean(account));

  return (
    <div className="page-stack">
      <PageHeader
        kicker="MEMORY WORKBENCH"
        title="记忆管理"
        description="管理全局与 Bot 专属 Memory，并审核自动整理的记忆草稿。"
        action={canCreate ? (tab === 'slang' ? '新增黑话' : '新增记忆') : tab === 'slang' ? '新增黑话' : null}
        actionIcon={Plus}
        onAction={
          tab === 'slang'
            ? () => setEditor({ term: '', meaning: '', status: 'candidate' })
            : newMemory
        }
      />

      {error ? (
        <div className="app-alert" role="alert">
          <span className="app-alert__bar" aria-hidden="true" />
          {error}
        </div>
      ) : null}

      <Card bare>
        <div className="memory-page__tabs">
          <Tabs items={memoryTabs} value={tab} onChange={setTab} />
        </div>

        {['global', 'bot'].includes(tab) ? (
          <div className="memory-page__body">
            {tab === 'bot' ? (
              <div className="memory-page__botbar">
                <SelectField
                  label="Bot 账号"
                  value={accountId}
                  options={accounts.map((row) => row.id)}
                  labels={accounts.map(
                    (row) => `${row.name || row.bot_id} · ${row.platform} / ${row.bot_id}`,
                  )}
                  onChange={setAccountId}
                />
                {account ? (
                  <>
                    <CheckRow
                      label="自动整理待审核记忆"
                      checked={botSettings.enabled}
                      onChange={(checked) => setBotSettings({ ...botSettings, enabled: checked })}
                    />
                    <Field
                      label="收到消息数量"
                      type="number"
                      min={1}
                      max={1000}
                      value={botSettings.interval}
                      onChange={(next) => setBotSettings({ ...botSettings, interval: next })}
                    />
                    <Button
                      variant="soft"
                      size="sm"
                      loading={savingSettings}
                      onClick={saveBotSettings}
                    >
                      保存 Bot 设置
                    </Button>
                  </>
                ) : null}
              </div>
            ) : null}

            {tab === 'bot' && !account ? (
              <EmptyState
                title="还没有 Bot 账号"
                detail="添加平台账号后，可为每个 Bot 单独维护 Memory。"
              />
            ) : loading ? (
              <SkeletonRows rows={4} />
            ) : (
              <div className={`memory-page__layout${tab === 'global' ? ' memory-page__layout--index' : ''}`}>
                {memories.length ? (
                  <DataTable layout="minmax(220px, 1.4fr) minmax(180px, 1fr) 96px" minWidth={640}>
                    <div className="ui-table__head">
                      <span>记忆</span>
                      <span>说明</span>
                      <span className="ui-table__head-end">操作</span>
                    </div>
                    {memories.map((row, rowIndex) => (
                      <DataRow key={row.name} index={rowIndex}>
                        <IdentityCell
                          icon={BookOpen}
                          title={row.title}
                          subtitle={`${row.name} · ${row.type} · ${row.chars} 字`}
                        />
                        <Cell>{row.description}</Cell>
                        <div className="ui-table__actions">
                          <Button
                            variant="icon"
                            size="sm"
                            icon={Pencil}
                            title="编辑"
                            aria-label="编辑记忆"
                            onClick={() => openMemory(row)}
                          />
                          <Button
                            variant="icon-danger"
                            size="sm"
                            icon={Trash2}
                            title="删除"
                            aria-label="删除记忆"
                            onClick={() => removeMemory(row.name)}
                          />
                        </div>
                      </DataRow>
                    ))}
                  </DataTable>
                ) : (
                  <EmptyState
                    title={tab === 'global' ? '还没有全局记忆' : '这个 Bot 还没有记忆'}
                    detail="添加长期有效的信息；自动总结的内容需先在待审核列表中通过。"
                  />
                )}

                {tab === 'global' ? (
                  <aside className="memory-page__index">
                    <span className="section-label">Memory.md 索引</span>
                    <pre className="code-block">{index || '索引为空，新增记忆后会自动生成。'}</pre>
                  </aside>
                ) : null}
              </div>
            )}
          </div>
        ) : null}

        {tab === 'review' ? (
          <div className="memory-page__body">
            {loading ? (
              <SkeletonRows rows={4} />
            ) : queue.length ? (
              <DataTable layout="minmax(220px, 1.3fr) minmax(220px, 1.3fr) 220px" minWidth={720}>
                <div className="ui-table__head">
                  <span>草稿</span>
                  <span>摘要</span>
                  <span className="ui-table__head-end">操作</span>
                </div>
                {queue.map((row, rowIndex) => (
                  <DataRow key={row.id} index={rowIndex}>
                    <IdentityCell
                      icon={BookOpen}
                      tone="amber"
                      title={row.title}
                      subtitle={`${row.platform} / ${row.bot_id} · ${row.source_messages} 条消息 · ${formatTime(row.created_at)}`}
                    />
                    <Cell>
                      {row.description}
                      <br />
                      {row.content}
                    </Cell>
                    <div className="ui-table__actions">
                      <Button variant="soft" size="sm" onClick={() => approveCandidate(row)}>
                        通过
                      </Button>
                      <Button
                        variant="icon"
                        size="sm"
                        icon={Pencil}
                        title="编辑"
                        aria-label="编辑草稿"
                        onClick={() =>
                          setEditor({ ...row, queueId: row.id, name: row.name || memorySlug(row.title) })
                        }
                      />
                      <Button
                        variant="icon-danger"
                        size="sm"
                        icon={Trash2}
                        title="删除"
                        aria-label="删除草稿"
                        onClick={() => removeCandidate(row.id)}
                      />
                    </div>
                  </DataRow>
                ))}
              </DataTable>
            ) : (
              <EmptyState
                title="没有待审核记忆"
                detail="Bot 按账号设置的消息数量整理出草稿后，会显示在这里。"
              />
            )}
          </div>
        ) : null}

        {tab === 'slang' ? (
          <div className="memory-page__body">
            <SlangSettings
              settings={settings}
              providers={providers}
              reviewDraft={reviewDraft}
              onDraftChange={setReviewDraft}
              onToggleEnabled={(checked) => updateSettings({ ...settings, enabled: checked })}
              onSave={saveReviewSettings}
            />

            {loading ? (
              <SkeletonRows rows={4} />
            ) : slang.length ? (
              <DataTable layout="minmax(200px, 1.1fr) minmax(240px, 1.4fr) 260px" minWidth={720}>
                <div className="ui-table__head">
                  <span>词条</span>
                  <span>含义</span>
                  <span className="ui-table__head-end">操作</span>
                </div>
                {slang.map((row, rowIndex) => (
                  <DataRow key={row.id} index={rowIndex}>
                    <IdentityCell
                      icon={MessageSquareText}
                      tone="blossom"
                      title={row.term}
                      subtitle={`${
                        row.status === 'confirmed'
                          ? '已确认'
                          : row.status === 'rejected'
                            ? '已忽略'
                            : '待审核'
                      }${
                        row.reviewer
                          ? ` · ${
                              row.reviewer === 'auto'
                                ? '自动放行'
                                : row.reviewer === 'manual'
                                  ? '人工复议'
                                  : '审核未判定'
                            }`
                          : ''
                      }`}
                    />
                    <Cell>
                      {row.meaning || '尚未补充'}
                      {row.review_reason ? ` · ${row.review_reason}` : ''}
                    </Cell>
                    <div className="ui-table__actions">
                      <Button variant="soft" size="sm" onClick={() => reviewSlang(row)}>
                        {row.status === 'confirmed' ? '标为待审核' : '确认词条'}
                      </Button>
                      <Button
                        variant="icon"
                        size="sm"
                        icon={Pencil}
                        title="编辑"
                        aria-label="编辑词条"
                        onClick={() => setEditor({ ...row })}
                      />
                      <Button
                        variant="icon-danger"
                        size="sm"
                        icon={Trash2}
                        title="删除"
                        aria-label="删除词条"
                        onClick={() => removeSlang(row.id)}
                      />
                    </div>
                  </DataRow>
                ))}
              </DataTable>
            ) : (
              <EmptyState
                title="还没有黑话词条"
                detail="自动学习或手动添加的群聊用语会显示在这里。"
              />
            )}
          </div>
        ) : null}
      </Card>

      {showMemoryEditor || editor?.queueId ? (
        <MemoryEntryEditor
          title={editor.queueId ? '编辑待审核记忆' : `${tab === 'global' ? '全局' : 'Bot'} Memory`}
          editor={editor}
          onChange={(patch) => setEditor({ ...editor, ...patch })}
          onClose={() => setEditor(null)}
          onSave={saveMemory}
          busy={busy}
        />
      ) : null}

      {editor && tab === 'slang' ? (
        <SlangEntryEditor
          editor={editor}
          onChange={(patch) => setEditor({ ...editor, ...patch })}
          onClose={() => setEditor(null)}
          onSave={saveSlang}
          busy={busy}
          error={error}
        />
      ) : null}
    </div>
  );
}
