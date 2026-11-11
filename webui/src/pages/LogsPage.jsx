import { useEffect, useState } from 'react';
import {
  Activity,
  Check,
  MessageCircle,
  RefreshCw,
  Trash2,
  UsersRound,
} from 'lucide-react';
import Button from '../components/ui/Button.jsx';
import Card, { CardHeader } from '../components/ui/Card.jsx';
import EmptyState from '../components/ui/EmptyState.jsx';
import PageHeader from '../components/ui/PageHeader.jsx';
import Tabs from '../components/ui/Tabs.jsx';
import { SearchInput, SelectField } from '../components/ui/Field.jsx';
import { SkeletonRows } from '../components/ui/Skeleton.jsx';
import { useConfirm } from '../components/feedback/ConfirmProvider.jsx';
import { useToast } from '../components/feedback/ToastProvider.jsx';
import { api } from '../lib/api.js';
import {
  conversationLabel,
  conversationStatus,
  formatCost,
  formatTime,
  messageRoleLabel,
  messageText,
} from '../lib/format.js';
import './LogsPage.css';

const STATUS_OPTIONS = ['all', 'pending', 'approved', 'rejected'];
const STATUS_LABELS = ['全部状态', '待确认', '已确认', '已拒绝'];

export default function LogsPage({ token, snapshot }) {
  const [logs, setLogs] = useState({
    activity: snapshot.activity || [],
    usage: snapshot.usage || [],
    conversations: snapshot.conversations || [],
  });
  const [scope, setScope] = useState('all');
  const [status, setStatus] = useState('all');
  const [query, setQuery] = useState('');
  const [selectedKey, setSelectedKey] = useState('');
  const [detail, setDetail] = useState(null);
  const [busy, setBusy] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState('');
  const { confirm } = useConfirm();
  const toast = useToast();

  async function reload() {
    const next = await api(token, '/logs');
    setLogs(next);
    setError('');
    return next;
  }

  useEffect(() => {
    reload().catch((err) => setError(err.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const conversations = (logs.conversations || []).filter(
    (row) =>
      (scope === 'all' || row.kind === scope) &&
      (status === 'all' || (row.status || 'approved') === status) &&
      `${row.name || ''} ${row.peer_id} ${row.platform} ${row.bot_id}`
        .toLowerCase()
        .includes(query.trim().toLowerCase()),
  );

  useEffect(() => {
    if (!conversations.some((row) => row.key === selectedKey)) {
      setSelectedKey(conversations[0]?.key || '');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope, status, query, logs.conversations]);

  useEffect(() => {
    let active = true;
    setDetail(null);
    if (!selectedKey) {
      setLoadingDetail(false);
      return () => {
        active = false;
      };
    }
    setLoadingDetail(true);
    api(token, `/conversations/${selectedKey}`)
      .then((next) => {
        if (active) setDetail(next);
      })
      .catch((err) => {
        if (active) setError(err.message);
      })
      .finally(() => {
        if (active) setLoadingDetail(false);
      });
    return () => {
      active = false;
    };
  }, [token, selectedKey]);

  async function reviewConversation(nextStatus) {
    if (!selectedKey || detail?.key !== selectedKey) return;
    setBusy(true);
    setError('');
    try {
      await api(token, `/conversations/${selectedKey}/status`, 'PUT', { status: nextStatus });
      await reload();
      setDetail(await api(token, `/conversations/${selectedKey}`));
      toast.success(nextStatus === 'approved' ? '会话已确认' : '会话已拒绝');
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function clearConversation() {
    if (!selectedKey || detail?.key !== selectedKey) return;
    const ok = await confirm({
      title: '清空聊天记录',
      message: '确认清空这个会话的全部聊天记录？历史摘要会一并重置，且不可恢复。',
      confirmLabel: '清空记录',
      tone: 'danger',
    });
    if (!ok) return;
    setBusy(true);
    setError('');
    try {
      await api(token, `/conversations/${selectedKey}/reset`, 'POST');
      setDetail(await api(token, `/conversations/${selectedKey}`));
      await reload();
      toast.success('聊天记录已清空');
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        kicker="CONVERSATION LOG"
        title="对话日志"
        description={error || '筛选会话状态，确认新会话并查看 Agent 记录、活动流与用量。'}
      />

      <Card bare>
        <div className="logs-page__toolbar">
          <Tabs
            items={[
              { id: 'all', label: '全部' },
              { id: 'group', label: '群聊', icon: UsersRound },
              { id: 'private', label: '私聊', icon: MessageCircle },
            ]}
            value={scope}
            onChange={setScope}
            ariaLabel="会话范围"
          />
          <div className="logs-page__filters">
            <SelectField
              label="会话状态"
              value={status}
              options={STATUS_OPTIONS}
              labels={STATUS_LABELS}
              onChange={setStatus}
            />
            <SearchInput
              value={query}
              onChange={setQuery}
              placeholder="搜索名称、ID 或平台"
              label="搜索会话"
            />
            <Button
              variant="soft"
              size="sm"
              icon={RefreshCw}
              loading={busy}
              onClick={() => reload().catch((err) => setError(err.message))}
            >
              刷新记录
            </Button>
            <span className="text-faint">{conversations.length} 个会话</span>
          </div>
        </div>

        <div className="conversation">
          <aside className="conversation__list" aria-label="会话列表">
            {conversations.length ? (
              conversations.map((row, index) => {
                const active = selectedKey === row.key;
                return (
                  <button
                    key={row.key}
                    type="button"
                    className={`conversation__item${active ? ' is-active' : ''}`}
                    style={{ '--stagger-index': index }}
                    onClick={() => setSelectedKey(row.key)}
                  >
                    <span className="conversation__icon" aria-hidden="true">
                      {row.kind === 'group' ? <UsersRound size={15} /> : <MessageCircle size={15} />}
                    </span>
                    <span className="conversation__text">
                      <strong>{row.name || row.peer_id || '未知会话'}</strong>
                      <small>
                        {row.kind === 'group' ? '群聊' : '私聊'} · {row.platform} · {row.bot_id}
                      </small>
                      <small>{row.peer_id}</small>
                    </span>
                    <span
                      className={`conversation__status is-${
                        row.status === 'pending'
                          ? 'pending'
                          : row.status === 'rejected'
                            ? 'rejected'
                            : 'approved'
                      }`}
                      title={conversationStatus(row.status)}
                      aria-label={conversationStatus(row.status)}
                    />
                  </button>
                );
              })
            ) : (
              <EmptyState
                compact
                title="暂无会话"
                detail="收到群聊或私聊消息后，会话会显示在这里。"
              />
            )}
          </aside>

          <section className="conversation__panel">
            {loadingDetail ? (
              <SkeletonRows rows={4} />
            ) : detail ? (
              <>
                <header className="conversation__head">
                  <div>
                    <strong>{conversationLabel(detail)}</strong>
                    <small>
                      {detail.platform} · {detail.bot_id} · {detail.peer_id} ·{' '}
                      {conversationStatus(detail.status)}
                    </small>
                  </div>
                  <div className="inline-actions">
                    {detail.status !== 'approved' ? (
                      <Button
                        variant="soft"
                        size="sm"
                        icon={Check}
                        disabled={busy}
                        onClick={() => reviewConversation('approved')}
                      >
                        确认会话
                      </Button>
                    ) : null}
                    {detail.status !== 'rejected' ? (
                      <Button
                        variant="danger"
                        size="sm"
                        disabled={busy}
                        onClick={() => reviewConversation('rejected')}
                      >
                        拒绝
                      </Button>
                    ) : null}
                    <Button
                      variant="danger"
                      size="sm"
                      icon={Trash2}
                      loading={busy}
                      onClick={clearConversation}
                    >
                      清空聊天记录
                    </Button>
                  </div>
                </header>

                <div className="transcript">
                  {detail.messages?.length ? (
                    detail.messages.map((message, index) => (
                      <article
                        key={`${message.role}-${index}`}
                        className={`bubble bubble--${message.role}`}
                        style={{ '--stagger-index': index }}
                      >
                        <span className="bubble__role">{messageRoleLabel(message.role)}</span>
                        <div className="bubble__body">
                          {messageText(message.content) ||
                            (message.tool_calls?.length
                              ? `调用工具：${message.tool_calls.map((call) => call.name).join('、')}`
                              : '（空消息）')}
                        </div>
                      </article>
                    ))
                  ) : (
                    <EmptyState compact title="这个会话还没有消息" detail="新消息会自动出现在这里。" />
                  )}
                </div>
              </>
            ) : (
              <EmptyState
                title="选择一个会话"
                detail="从左侧选择群聊或私聊，查看对应的 Agent 记录。"
              />
            )}
          </section>
        </div>
      </Card>

      <div className="two-columns">
        <Card>
          <CardHeader icon={Activity} title="活动流" description="最近的桥接事件" tone="mint" />
          {logs.activity?.length ? (
            <div className="log-feed">
              {logs.activity
                .slice()
                .reverse()
                .slice(0, 20)
                .map((item, index) => (
                  <div className="log-feed__row" key={`${item.at}-${index}`}>
                    <span className="log-feed__time">{formatTime(item.at)}</span>
                    <span className="log-feed__text">{item.text}</span>
                  </div>
                ))}
            </div>
          ) : (
            <EmptyState compact title="暂无活动记录" detail="收到消息后会显示事件摘要。" />
          )}
        </Card>

        <Card>
          <CardHeader icon={Activity} title="用量记录" description="token 与估算成本" />
          {logs.usage?.length ? (
            <div className="log-feed">
              {logs.usage
                .slice()
                .reverse()
                .slice(0, 12)
                .map((item, index) => (
                  <div className="log-feed__row log-feed__row--usage" key={`${item.at}-${index}`}>
                    <div>
                      <strong>{item.conversation?.slice(0, 10) || 'session'}</strong>
                      <small>{formatTime(item.at)}</small>
                    </div>
                    <span>{item.total || 0} tokens</span>
                    <b>{formatCost(item.estimated_cost)}</b>
                  </div>
                ))}
            </div>
          ) : (
            <EmptyState compact title="暂无用量记录" detail="模型调用后会显示 token 与估算成本。" />
          )}
        </Card>
      </div>
    </div>
  );
}
