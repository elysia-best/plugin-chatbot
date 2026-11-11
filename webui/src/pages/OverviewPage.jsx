import {
  Activity,
  Bot,
  Gauge,
  MessageSquareText,
  Plus,
  Server,
  UsersRound,
} from 'lucide-react';
import Button from '../components/ui/Button.jsx';
import Card, { CardHeader } from '../components/ui/Card.jsx';
import EmptyState from '../components/ui/EmptyState.jsx';
import IconChip from '../components/ui/IconChip.jsx';
import PageHeader from '../components/ui/PageHeader.jsx';
import { SoftTag, StatePill } from '../components/ui/Badge.jsx';
import { useCountUp } from '../hooks/useCountUp.js';
import { formatTime } from '../lib/format.js';
import './OverviewPage.css';

function MetricCard({ label, value, detail, icon, tone, index }) {
  const display = useCountUp(value);
  return (
    <article
      className={`metric metric--${tone}`}
      style={{ '--stagger-index': index }}
    >
      <IconChip icon={icon} tone={tone} size="lg" className="metric__icon" />
      <span className="metric__label">{label}</span>
      <strong className="metric__value">{display}</strong>
      <span className="metric__detail">{detail}</span>
    </article>
  );
}

export default function OverviewPage({ snapshot, onNavigate }) {
  const accounts = snapshot.accounts || [];
  const groups = snapshot.groups || [];
  const providers = snapshot.interfaces?.providers || [];
  const activity = snapshot.activity || [];
  const enabledAccounts = accounts.filter((account) => account.enabled !== false).length;

  return (
    <div className="page-stack">
      <PageHeader
        kicker="RUNTIME OVERVIEW"
        title="今天的运行状态"
        description="账号、群聊、人格和接口能力都在这里保持清晰。"
      >
        <StatePill tone="indigo">
          <Activity size={14} />
          {snapshot.mode === 'agent' ? 'Agent 模式' : 'Chat 模式'}
        </StatePill>
      </PageHeader>

      <div className="metric-grid">
        <MetricCard
          index={0}
          label="运行账号"
          value={enabledAccounts}
          detail={`${accounts.length} 个已登记`}
          icon={Bot}
          tone="indigo"
        />
        <MetricCard
          index={1}
          label="群聊策略"
          value={groups.length}
          detail="按账号隔离"
          icon={UsersRound}
          tone="mint"
        />
        <MetricCard
          index={2}
          label="AI 接口"
          value={providers.length}
          detail="可自动发现模型"
          icon={Server}
          tone="amber"
        />
        <MetricCard
          index={3}
          label="活动记录"
          value={activity.length}
          detail="最近 100 条"
          icon={Gauge}
          tone="blossom"
        />
      </div>

      <div className="two-columns">
        <Card>
          <CardHeader
            icon={Bot}
            title="账号与群聊"
            description="每个 Bot 绑定的群聊策略"
            actions={
              <Button variant="ghost" size="sm" onClick={() => onNavigate('accounts')}>
                管理账号
              </Button>
            }
          />

          {accounts.length ? (
            <div className="account-tree anim-stagger">
              {accounts.map((account, index) => {
                const boundGroups = groups.filter(
                  (group) =>
                    group.platform === account.platform && group.bot_id === account.bot_id,
                );
                return (
                  <div
                    className="account-tree__item"
                    key={account.id}
                    style={{ '--stagger-index': index }}
                  >
                    <div className="account-tree__row">
                      <IconChip icon={Bot} tone="indigo" />
                      <div className="account-tree__text">
                        <strong>{account.name || account.bot_id}</strong>
                        <small>{account.platform}</small>
                      </div>
                      <SoftTag tone="slate">{account.bot_id}</SoftTag>
                    </div>
                    <div className="account-tree__groups">
                      {boundGroups.map((group) => (
                        <div className="account-tree__group" key={group.id}>
                          <MessageSquareText size={14} aria-hidden="true" />
                          <span>{group.name || group.group_id}</span>
                          <small>{group.group_id}</small>
                        </div>
                      ))}
                      <button
                        type="button"
                        className="account-tree__add"
                        onClick={() => onNavigate('groups')}
                      >
                        <Plus size={13} />
                        添加群聊策略
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <EmptyState
              title="还没有账号"
              detail="收到消息后会自动发现 Bot，也可以手动添加。"
              action="新增账号"
              onAction={() => onNavigate('accounts')}
            />
          )}
        </Card>

        <Card>
          <CardHeader
            icon={Activity}
            title="最近活动"
            description="桥接层最近的事件"
            tone="mint"
            actions={
              <Button variant="ghost" size="sm" onClick={() => onNavigate('logs')}>
                查看日志
              </Button>
            }
          />

          {activity.length ? (
            <div className="activity-feed anim-stagger">
              {activity
                .slice(-7)
                .reverse()
                .map((item, index) => (
                  <div
                    className="activity-feed__item"
                    key={`${item.at}-${index}`}
                    style={{ '--stagger-index': index }}
                  >
                    <span className="activity-feed__marker" aria-hidden="true">
                      <Activity size={14} />
                    </span>
                    <div>
                      <strong>{item.text}</strong>
                      <small>{formatTime(item.at)}</small>
                    </div>
                  </div>
                ))}
            </div>
          ) : (
            <EmptyState
              title="暂无活动"
              detail="有消息进入桥接后，活动会显示在这里。"
              compact
            />
          )}
        </Card>
      </div>
    </div>
  );
}
