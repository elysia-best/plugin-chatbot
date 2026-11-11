import { useMemo, useState } from 'react';
import { Plus, Trash2, UserPlus } from 'lucide-react';
import Button from '../../components/ui/Button.jsx';
import { Field, SelectField, SearchInput } from '../../components/ui/Field.jsx';
import EmptyState from '../../components/ui/EmptyState.jsx';
import { SoftTag } from '../../components/ui/Badge.jsx';
import './AccessLists.css';

const LIST_LABELS = [
  ['admins', '管理员'],
  ['whitelist', '白名单'],
  ['blacklist', '黑名单'],
];

/**
 * 账号访问名单编辑器：管理员 / 白名单 / 黑名单。
 * 名称优先采用 adapter 昵称，ID 用于精确匹配；修改随账号一并保存。
 */
export default function AccessLists({ value, snapshot, onChange }) {
  const [filter, setFilter] = useState('');
  const [draft, setDraft] = useState({ id: '', name: '', kind: 'private', list: 'whitelist' });

  const conversations = snapshot?.conversations || [];
  const groups = snapshot?.groups || [];

  const users = useMemo(() => {
    const raw = Array.isArray(value.private_users) ? value.private_users : [];
    return raw
      .map((item) =>
        typeof item === 'object' && item
          ? { ...item, id: String(item.id || '') }
          : { id: String(item || ''), name: '' },
      )
      .filter((item) => item.id);
  }, [value.private_users]);

  const sameAccount = (row) =>
    String(row.platform || row.adapter || '')
      .trim()
      .toLowerCase() ===
      String(value.platform || value.adapter || '')
        .trim()
        .toLowerCase() && String(row.bot_id || '') === String(value.bot_id || '');

  const adapterName = (name, id) => {
    const text = String(name || '').trim();
    return text && text !== String(id) ? text : '';
  };

  const candidates = useMemo(() => {
    const byIdentity = new Map();
    const addCandidate = (candidate) => {
      const id = String(candidate.id || '').trim();
      if (!id) return;
      const key = `${candidate.kind || 'private'}:${id}`;
      const previous = byIdentity.get(key);
      const name = adapterName(candidate.name, id);
      byIdentity.set(key, {
        ...previous,
        ...candidate,
        id,
        name: name || previous?.name || '',
      });
    };

    if (draft.list === 'admins' || draft.kind === 'private') {
      users.forEach((user) => addCandidate({ ...user, kind: 'private' }));
      conversations
        .filter((row) => sameAccount(row) && row.kind === 'private')
        .forEach((row) => {
          const id = row.user_id || row.peer_id;
          addCandidate({ id, name: adapterName(row.name, id), kind: 'private' });
        });
    }

    if (draft.list !== 'admins' && draft.kind === 'group') {
      groups.filter(sameAccount).forEach((row) =>
        addCandidate({ id: row.group_id, name: adapterName(row.name, row.group_id), kind: 'group' }),
      );
      conversations
        .filter((row) => sameAccount(row) && row.kind === 'group')
        .forEach((row) =>
          addCandidate({ id: row.peer_id, name: adapterName(row.name, row.peer_id), kind: 'group' }),
        );
    }

    return [...byIdentity.values()].sort((a, b) =>
      (a.name || a.id).localeCompare(b.name || b.id, 'zh-CN'),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft.list, draft.kind, users, groups, conversations, value.platform, value.adapter, value.bot_id]);

  const normalizedList = (list, defaultKind) =>
    (Array.isArray(value[list]) ? value[list] : [])
      .map((item) => {
        if (item && typeof item === 'object') {
          return { ...item, id: String(item.id || ''), kind: item.kind || defaultKind };
        }
        return { id: String(item || ''), name: '', kind: defaultKind };
      })
      .filter((item) => item.id);

  const adapterDisplayName = (row) => {
    const id = String(row.id);
    const kind = row.kind || 'private';
    if (kind === 'group') {
      const group = groups.find((item) => sameAccount(item) && String(item.group_id) === id);
      const conversation = conversations.find(
        (item) => sameAccount(item) && item.kind === 'group' && String(item.peer_id) === id,
      );
      return adapterName(group?.name, id) || adapterName(conversation?.name, id);
    }
    return (
      adapterName(users.find((item) => item.id === id)?.name, id) ||
      adapterName(
        conversations.find(
          (item) =>
            sameAccount(item) &&
            item.kind === 'private' &&
            (String(item.user_id) === id || String(item.peer_id) === id),
        )?.name,
        id,
      )
    );
  };

  const displayName = (row) =>
    adapterDisplayName(row) || adapterName(row.name, row.id) || String(row.id);

  const append = (list, row) => {
    const defaultKind = list === 'admins' ? 'private' : draft.kind;
    const existing = normalizedList(list, defaultKind);
    const duplicated = existing.some(
      (item) => item.id === String(row.id) && (list === 'admins' || item.kind === row.kind),
    );
    if (!duplicated) onChange({ [list]: [...existing, { ...row, id: String(row.id) }] });
  };

  function add() {
    const id = draft.id.trim();
    if (!id) return;
    const kind = draft.list === 'admins' ? 'private' : draft.kind;
    const candidate = candidates.find((item) => item.id === id && item.kind === kind);
    append(draft.list, { id, name: draft.name.trim() || candidate?.name || '', kind });
    setDraft({ ...draft, id: '', name: '' });
  }

  function remove(list, row) {
    const defaultKind = list === 'admins' ? 'private' : row.kind || 'private';
    onChange({
      [list]: normalizedList(list, defaultKind).filter(
        (item) =>
          item.id !== String(row.id) || (list !== 'admins' && item.kind !== (row.kind || 'private')),
      ),
    });
  }

  const adminIds = new Set(normalizedList('admins', 'private').map((item) => item.id));
  const filterText = filter.trim().toLowerCase();
  const matches = (row) => `${row.id} ${displayName(row)}`.toLowerCase().includes(filterText);
  const recentUsers = users.filter((row) =>
    `${row.id} ${row.name || ''}`.toLowerCase().includes(filterText),
  );

  return (
    <section className="access">
      <header className="access__head">
        <div>
          <h4>访问名单</h4>
          <p>显示名称优先采用 adapter 昵称，ID 用于精确匹配；修改后点击「保存设置」生效。</p>
        </div>
      </header>

      <div className="access__composer">
        <div className="form-grid form-grid--three">
          <SelectField
            label="名单"
            value={draft.list}
            options={LIST_LABELS.map(([id]) => id)}
            labels={LIST_LABELS.map(([, label]) => label)}
            onChange={(list) => setDraft({ ...draft, list, id: '', name: '' })}
          />
          <SelectField
            label="会话类型"
            value={draft.list === 'admins' ? 'private' : draft.kind}
            options={['private', 'group']}
            labels={['私聊用户', '群聊']}
            onChange={(kind) => setDraft({ ...draft, kind, id: '', name: '' })}
          />
          <Field
            label="用户 / 群 ID"
            value={draft.id}
            onChange={(id) => {
              const candidate = candidates.find((row) => row.id === id);
              setDraft({ ...draft, id, name: candidate?.name || '' });
            }}
            placeholder="可直接输入 ID"
          />
          <SelectField
            wide
            label={draft.kind === 'group' && draft.list !== 'admins' ? '选择已发现群聊' : '选择已发现私聊'}
            value={draft.id}
            options={['', ...candidates.map((row) => row.id)]}
            labels={[
              candidates.length ? '选择名称或 ID' : '暂无可选对象，可手动输入 ID',
              ...candidates.map((row) => `${row.name || row.id} · ${row.id}`),
            ]}
            onChange={(id) => {
              const candidate = candidates.find((row) => row.id === id);
              setDraft({ ...draft, id, name: candidate?.name || '' });
            }}
          />
          <Field
            wide
            label="显示名称（可选，留空则使用 adapter 昵称或 ID）"
            value={draft.name}
            onChange={(name) => setDraft({ ...draft, name })}
            placeholder="例如：值班管理员"
          />
        </div>

        <div className="access__composer-actions">
          <Button variant="soft" size="sm" icon={Plus} onClick={add} disabled={!draft.id.trim()}>
            加入名单
          </Button>
          <SearchInput
            value={filter}
            onChange={setFilter}
            placeholder="筛选名单：搜索 ID 或名称"
            label="筛选名单"
          />
        </div>
      </div>

      <div className="access__lists">
        {LIST_LABELS.map(([list, label]) => {
          const rows = normalizedList(list, 'private').filter(matches);
          return (
            <div className="access__list" key={list}>
              <div className="access__list-head">
                <strong>{label}</strong>
                <span className="ui-count ui-count--slate">{rows.length}</span>
              </div>
              {rows.length ? (
                rows.map((row) => (
                  <div className="access__row" key={`${row.kind}-${row.id}`}>
                    <SoftTag tone={row.kind === 'group' ? 'mint' : 'indigo'}>
                      {row.kind === 'group' ? '群聊' : '私聊'}
                    </SoftTag>
                    <div className="access__row-text">
                      <strong>{displayName(row)}</strong>
                      <small>{row.id}</small>
                    </div>
                    <Button
                      variant="icon-danger"
                      size="sm"
                      icon={Trash2}
                      title="移出名单"
                      aria-label="移出名单"
                      onClick={() => remove(list, row)}
                    />
                  </div>
                ))
              ) : (
                <p className="access__empty">暂无条目</p>
              )}
            </div>
          );
        })}
      </div>

      <div className="access__list access__list--wide">
        <div className="access__list-head">
          <strong>最近私聊用户</strong>
          <span className="ui-count ui-count--slate">{users.length}</span>
        </div>
        {recentUsers.length ? (
          recentUsers.map((row) => {
            const name =
              adapterDisplayName({ ...row, kind: 'private' }) || adapterName(row.name, row.id) || row.id;
            return (
              <div className="access__row" key={row.id}>
                <span className="access__avatar" aria-hidden="true">
                  <UserPlus size={15} />
                </span>
                <div className="access__row-text">
                  <strong>{name}</strong>
                  <small>{row.id}</small>
                </div>
                <Button
                  variant="soft"
                  size="sm"
                  disabled={adminIds.has(row.id)}
                  onClick={() =>
                    append('admins', {
                      id: row.id,
                      name: adapterDisplayName({ ...row, kind: 'private' }) || row.name,
                      kind: 'private',
                    })
                  }
                >
                  {adminIds.has(row.id) ? '已是管理员' : '设为管理员'}
                </Button>
              </div>
            );
          })
        ) : (
          <EmptyState
            compact
            title="还没有私聊用户"
            detail="收到一条私聊消息后，可从这里直接设为管理员。"
          />
        )}
      </div>
    </section>
  );
}
