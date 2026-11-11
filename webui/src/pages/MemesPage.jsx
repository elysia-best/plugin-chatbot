import { useEffect, useRef, useState } from 'react';
import { CircleAlert, Image as ImageIcon, Pencil, Trash2, Upload } from 'lucide-react';
import Button from '../components/ui/Button.jsx';
import Card, { CardHeader } from '../components/ui/Card.jsx';
import EmptyState from '../components/ui/EmptyState.jsx';
import Modal, { ModalFooter } from '../components/ui/Modal.jsx';
import PageHeader from '../components/ui/PageHeader.jsx';
import { CheckRow, Field, SearchInput } from '../components/ui/Field.jsx';
import { SoftTag } from '../components/ui/Badge.jsx';
import Skeleton from '../components/ui/Skeleton.jsx';
import { useConfirm } from '../components/feedback/ConfirmProvider.jsx';
import { useToast } from '../components/feedback/ToastProvider.jsx';
import { api, apiBlob } from '../lib/api.js';
import { formatBytes } from '../lib/format.js';
import './MemesPage.css';

const MEME_TOOLS = ['chat_list_memes', 'chat_save_meme', 'chat_send_meme'];
const ACCEPT = 'image/png,image/jpeg,image/gif,image/webp';

export default function MemesPage({ token, tools, onNavigate, onRefresh }) {
  const [rows, setRows] = useState([]);
  const [settings, setSettings] = useState({ upload_enabled: true, max_bytes: 0 });
  const [query, setQuery] = useState('');
  const [thumbs, setThumbs] = useState({});
  const [editor, setEditor] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const thumbsRef = useRef({});
  const fileRef = useRef(null);
  const { confirm } = useConfirm();
  const toast = useToast();

  async function reload() {
    setLoading(true);
    try {
      const [list, config] = await Promise.all([api(token, '/memes'), api(token, '/memes/settings')]);
      setRows(list);
      setSettings(config);
      setError('');
      const next = {};
      await Promise.all(
        list.map(async (row) => {
          try {
            next[row.file] = URL.createObjectURL(
              await apiBlob(token, `/memes/image/${encodeURIComponent(row.file)}`),
            );
          } catch {
            /* 缩略图失败时保留占位图标 */
          }
        }),
      );
      Object.values(thumbsRef.current).forEach((url) => URL.revokeObjectURL(url));
      thumbsRef.current = next;
      setThumbs(next);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    reload();
    return () => {
      Object.values(thumbsRef.current).forEach((url) => URL.revokeObjectURL(url));
      thumbsRef.current = {};
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function upload(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (settings.max_bytes && file.size > settings.max_bytes) {
      setError('图片超过大小限制');
      event.target.value = '';
      return;
    }
    setBusy(true);
    setError('');
    try {
      const data = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(file);
      });
      await api(token, '/memes', 'POST', { name: file.name.replace(/\.[^.]+$/, ''), data });
      await reload();
      await onRefresh();
      toast.success('表情包已上传');
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
      event.target.value = '';
    }
  }

  async function saveEditor() {
    setBusy(true);
    try {
      await api(token, `/memes/${encodeURIComponent(editor.file)}`, 'PUT', {
        name: editor.name.trim(),
        keywords: editor.keywords,
        summary: editor.summary,
      });
      setEditor(null);
      await reload();
      toast.success('表情包信息已更新');
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(row) {
    const ok = await confirm({
      title: '删除表情包',
      message: `确认删除表情包「${row.name}」？图片文件会一并删除。`,
      confirmLabel: '删除',
      tone: 'danger',
    });
    if (!ok) return;
    try {
      await api(token, `/memes/${encodeURIComponent(row.file)}`, 'DELETE');
      await reload();
      toast.success('表情包已删除');
    } catch (err) {
      setError(err.message);
    }
  }

  async function toggleUpload(checked) {
    try {
      setSettings(await api(token, '/memes/settings', 'PUT', { upload_enabled: checked }));
    } catch (err) {
      setError(err.message);
    }
  }

  const keyword = query.trim().toLowerCase();
  const visible = keyword
    ? rows.filter((row) =>
        `${row.name} ${(row.keywords || []).join(' ')} ${row.summary || ''}`
          .toLowerCase()
          .includes(keyword),
      )
    : rows;

  return (
    <div className="page-stack">
      <PageHeader
        kicker="MEME LIBRARY"
        title="表情包"
        description={error || `${rows.length} 张表情；上传后可在聊天里通过 chat_send_meme 发送。`}
        action="上传图片"
        actionIcon={Upload}
        onAction={() => fileRef.current?.click()}
      />

      <input
        ref={fileRef}
        type="file"
        accept={ACCEPT}
        className="visually-hidden"
        disabled={busy || !settings.upload_enabled}
        onChange={upload}
        aria-label="选择表情包图片"
      />

      <Card bare>
        <div className="memes-page__toolbar">
          <SearchInput
            value={query}
            onChange={setQuery}
            placeholder="搜索名称、关键词或简介"
            label="搜索表情包"
          />
          <div className="memes-page__toolbar-actions">
            <CheckRow
              label="允许新增表情包"
              description="同时作用于 WebUI 与 chat_save_meme"
              checked={settings.upload_enabled}
              onChange={toggleUpload}
            />
            <Button
              variant="soft"
              size="sm"
              icon={Upload}
              disabled={busy || !settings.upload_enabled}
              onClick={() => fileRef.current?.click()}
            >
              选择图片
            </Button>
            <span className="text-faint">
              单图上限 {formatBytes(settings.max_bytes)} · {busy ? '上传中…' : '就绪'}
            </span>
          </div>
        </div>

        {loading ? (
          <div className="meme-grid">
            {Array.from({ length: 6 }).map((_, index) => (
              <div className="meme-card" key={index}>
                <Skeleton height={140} radius={16} />
                <Skeleton width="60%" height={13} />
                <Skeleton width="40%" height={10} />
              </div>
            ))}
          </div>
        ) : visible.length ? (
          <div className="meme-grid anim-stagger">
            {visible.map((row, index) => (
              <article className="meme-card" key={row.file} style={{ '--stagger-index': index }}>
                <div className="meme-card__thumb">
                  {thumbs[row.file] ? (
                    <img src={thumbs[row.file]} alt={row.name} loading="lazy" />
                  ) : (
                    <ImageIcon size={22} />
                  )}
                </div>
                <div className="meme-card__meta">
                  <strong>{row.name}</strong>
                  <small>
                    {row.file} · {formatBytes(row.bytes)}
                  </small>
                  <p>{row.summary || '暂无简介'}</p>
                  <div className="meme-card__tags">
                    {(row.keywords || []).map((tag) => (
                      <SoftTag key={tag} tone="blossom">
                        {tag}
                      </SoftTag>
                    ))}
                  </div>
                </div>
                <div className="meme-card__actions">
                  <Button
                    variant="icon"
                    size="sm"
                    icon={Pencil}
                    title="编辑"
                    aria-label="编辑表情包"
                    onClick={() =>
                      setEditor({ ...row, keywords: (row.keywords || []).join('、') })
                    }
                  />
                  <Button
                    variant="icon-danger"
                    size="sm"
                    icon={Trash2}
                    title="删除"
                    aria-label="删除表情包"
                    onClick={() => remove(row)}
                  />
                </div>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState
            icon={ImageIcon}
            title="还没有表情包"
            detail="上传图片，或让 Bot 在聊天里通过 chat_save_meme 保存。"
            action="上传图片"
            actionIcon={Upload}
            onAction={() => fileRef.current?.click()}
          />
        )}
      </Card>

      <Card>
        <CardHeader
          icon={ImageIcon}
          title="工具开关"
          description="在平台账号 / 群聊策略编辑器的「工具默认」中勾选；会话级覆盖使用对话日志里的会话工具设置。"
          tone="blossom"
        />
        <div className="memes-page__tools">
          <div className="memes-page__tags">
            {MEME_TOOLS.map((name) => (
              <SoftTag key={name} tone={(tools || []).some((tool) => tool.name === name) ? 'mint' : 'slate'}>
                {name} · {(tools || []).some((tool) => tool.name === name) ? '可用' : '未列出'}
              </SoftTag>
            ))}
          </div>
          <div className="inline-actions">
            <Button variant="soft" size="sm" onClick={() => onNavigate('accounts')}>
              平台账号
            </Button>
            <Button variant="soft" size="sm" onClick={() => onNavigate('groups')}>
              群聊策略
            </Button>
            <Button variant="soft" size="sm" onClick={() => onNavigate('logs')}>
              会话工具
            </Button>
          </div>
        </div>
      </Card>

      {editor ? (
        <Modal title="编辑表情包" kicker="MEME" onClose={() => setEditor(null)}>
          <div className="form-grid form-grid--two">
            <Field
              label="名称"
              value={editor.name}
              onChange={(value) => setEditor({ ...editor, name: value })}
            />
            <Field
              label="关键词（逗号或顿号分隔）"
              value={editor.keywords}
              onChange={(value) => setEditor({ ...editor, keywords: value })}
            />
            <Field
              label="简介"
              wide
              type="textarea"
              rows={4}
              value={editor.summary}
              onChange={(value) => setEditor({ ...editor, summary: value })}
            />
          </div>
          {error ? (
            <div className="form-error">
              <CircleAlert size={15} />
              {error}
            </div>
          ) : null}
          <ModalFooter onClose={() => setEditor(null)} onSave={saveEditor} busy={busy} />
        </Modal>
      ) : null}
    </div>
  );
}
