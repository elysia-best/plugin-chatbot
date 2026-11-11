import { useState } from 'react';
import { ArrowRight, CircleAlert, Eye, EyeOff, KeyRound, ShieldCheck, Sparkles } from 'lucide-react';
import { api, storeToken } from '../lib/api.js';
import './LoginPage.css';

/** 登录页：柔和渐变光斑 + 令牌校验，令牌仅保存在当前浏览器会话。 */
export default function LoginPage({ onLogin, notice }) {
  const [token, setToken] = useState('');
  const [visible, setVisible] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    const next = token.trim();
    if (!next) return;
    setBusy(true);
    setError('');
    try {
      await api(next, '/status');
      storeToken(next);
      onLogin(next);
    } catch (err) {
      setError(err?.message || '令牌无效');
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login">
      <div className="login__glow login__glow--indigo" aria-hidden="true" />
      <div className="login__glow login__glow--blossom" aria-hidden="true" />

      <section className="login__intro">
        <div className="login__brand">
          <span className="login__mark" aria-hidden="true">
            <Sparkles size={20} strokeWidth={2.1} />
          </span>
          <div>
            <strong>Chatbot</strong>
            <span>control room</span>
          </div>
        </div>

        <div className="login__copy">
          <span className="kicker">NONEBOT / ALCONNA</span>
          <h1>
            让每个账号，
            <br />
            <em>拥有自己的节奏。</em>
          </h1>
          <p>跨平台管理 Bot、人格、群聊策略与模型能力，所有改动即时生效。</p>
        </div>

        <div className="login__foot">
          <span className="login__dot" aria-hidden="true" />
          服务端已准备好
          <span className="login__rule" aria-hidden="true" />
          v0.1.0
        </div>
      </section>

      <section className="login__panel">
        <div className="login__card">
          <span className="login__icon" aria-hidden="true">
            <ShieldCheck size={24} strokeWidth={2} />
          </span>
          <span className="kicker">SECURE ACCESS</span>
          <h2>进入控制台</h2>
          <p className="login__hint">使用控制台访问令牌继续。</p>

          <form className="login__form" onSubmit={submit}>
            <label className="ui-field" htmlFor="access-token">
              <span className="ui-field__label">访问令牌</span>
              <span className="login__input">
                <KeyRound size={17} className="login__input-icon" aria-hidden="true" />
                <input
                  id="access-token"
                  className="login__input-control"
                  type={visible ? 'text' : 'password'}
                  value={token}
                  autoFocus
                  autoComplete="current-password"
                  placeholder="输入访问令牌"
                  onChange={(event) => setToken(event.target.value)}
                />
                <button
                  type="button"
                  className="login__reveal"
                  aria-label={visible ? '隐藏令牌' : '显示令牌'}
                  onClick={() => setVisible((current) => !current)}
                >
                  {visible ? <EyeOff size={17} /> : <Eye size={17} />}
                </button>
              </span>
            </label>

            {error || notice ? (
              <div className="login__error" role="alert">
                <CircleAlert size={15} />
                {error || notice}
              </div>
            ) : null}

            <button
              type="submit"
              className="ui-button ui-button--primary ui-button--lg ui-button--block login__submit"
              disabled={busy || !token.trim()}
              aria-busy={busy || undefined}
            >
              {busy ? <span className="ui-button__spinner" aria-hidden="true" /> : null}
              <span>{busy ? '验证中…' : '进入控制台'}</span>
              {busy ? null : <ArrowRight size={16} />}
            </button>
          </form>

          <p className="login__note">令牌只保存在当前浏览器会话中，关闭标签页即失效。</p>
        </div>
      </section>
    </main>
  );
}
