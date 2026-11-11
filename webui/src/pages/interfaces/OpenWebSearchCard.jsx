import { useEffect, useState } from 'react';
import { CircleAlert, RefreshCw, Server } from 'lucide-react';
import Button from '../../components/ui/Button.jsx';
import { CheckRow, Field } from '../../components/ui/Field.jsx';
import { SoftTag, StatusBadge } from '../../components/ui/Badge.jsx';
import { api } from '../../lib/api.js';
import './OpenWebSearchCard.css';

/** 内置搜索 MCP：服务地址写入顶层 mcp_server_url，清空即禁用。 */
export default function OpenWebSearchCard({ token }) {
  const [status, setStatus] = useState({ url: '', connected: false, error: '', tools: [] });
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let alive = true;
    api(token, '/mcp')
      .then((next) => {
        if (!alive) return;
        setStatus(next);
        setDraft(next.url || '');
      })
      .catch((err) => {
        if (alive) setError(err.message);
      });
    return () => {
      alive = false;
    };
  }, [token]);

  async function connect(value) {
    setBusy(true);
    setError('');
    try {
      const next = await api(token, '/mcp', 'PUT', { value });
      setStatus(next);
      setDraft(next.url || '');
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const enabled = Boolean(status.url);

  return (
    <section className="mcp-card">
      <header className="mcp-card__head">
        <div className="mcp-card__title">
          <span className="mcp-card__icon" aria-hidden="true">
            <Server size={18} />
          </span>
          <div>
            <span className="kicker">BUILT-IN MCP</span>
            <strong>open_websearch</strong>
            <small>内置搜索 MCP；清空服务地址即禁用。工具在会话的工具配置中单独启用。</small>
          </div>
        </div>
        <StatusBadge enabled={status.connected} onLabel="已连接" offLabel="未连接" />
      </header>

      <div className="mcp-card__controls">
        <CheckRow
          label="启用内置 MCP"
          checked={enabled}
          onChange={(checked) => {
            if (!checked) {
              connect('');
              return;
            }
            const next = draft || status.url || 'http://localhost:3000/mcp';
            setDraft(next);
            connect(next);
          }}
        />
        <Field
          label="服务地址"
          value={draft}
          onChange={setDraft}
          placeholder="http://localhost:3000/mcp"
          name="mcp-url"
        />
        <Button
          variant="soft"
          icon={RefreshCw}
          loading={busy}
          onClick={() => connect(draft.trim())}
        >
          {busy ? '连接中…' : '连接 / 重新发现'}
        </Button>
      </div>

      {error || status.error ? (
        <div className="form-error">
          <CircleAlert size={15} />
          {error || status.error}
        </div>
      ) : null}

      <div className="mcp-card__tools">
        <span className="text-faint">已发现 {status.tools?.length || 0} 个工具</span>
        {(status.tools || []).map((tool) => (
          <SoftTag key={tool.name} tone="indigo">
            {tool.name}
          </SoftTag>
        ))}
      </div>
    </section>
  );
}
