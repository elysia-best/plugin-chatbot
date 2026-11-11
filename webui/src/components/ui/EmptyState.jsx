import { Inbox } from 'lucide-react';
import Button from './Button.jsx';
import './EmptyState.css';

/** 空状态：柔和图标块 + 说明 + 可选行动，避免出现空白区域。 */
export default function EmptyState({
  title,
  detail,
  icon: Icon = Inbox,
  action,
  onAction,
  actionIcon,
  compact = false,
}) {
  return (
    <div className={`ui-empty${compact ? ' ui-empty--compact' : ''}`}>
      <span className="ui-empty__icon" aria-hidden="true">
        <Icon size={22} strokeWidth={1.9} />
      </span>
      <strong className="ui-empty__title">{title}</strong>
      {detail ? <p className="ui-empty__detail">{detail}</p> : null}
      {action ? (
        <Button variant="soft" size="sm" icon={actionIcon} onClick={onAction}>
          {action}
        </Button>
      ) : null}
    </div>
  );
}
