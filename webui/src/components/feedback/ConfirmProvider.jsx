import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react';
import { CircleAlert } from 'lucide-react';
import Modal from '../ui/Modal.jsx';
import Button from '../ui/Button.jsx';
import './ConfirmProvider.css';

const ConfirmContext = createContext(null);

const INITIAL = {
  open: false,
  mode: 'confirm',
  title: '',
  message: '',
  confirmLabel: '确认',
  tone: 'indigo',
  defaultValue: '',
  placeholder: '',
};

/**
 * 统一确认 / 输入浮层：替代浏览器原生 confirm 与 prompt，
 * 语义保持不变（阻塞式二次确认），视觉与动效统一到柔和界面风。
 */
export function ConfirmProvider({ children }) {
  const [state, setState] = useState(INITIAL);
  const [draft, setDraft] = useState('');
  const resolverRef = useRef(null);

  const confirm = useCallback((options) => {
    const config = typeof options === 'string' ? { message: options } : options || {};
    setState({
      ...INITIAL,
      ...config,
      open: true,
      mode: 'confirm',
      title: config.title || '请确认',
      confirmLabel: config.confirmLabel || '确认',
    });
    return new Promise((resolve) => {
      resolverRef.current = resolve;
    });
  }, []);

  const prompt = useCallback((options) => {
    const config = typeof options === 'string' ? { message: options } : options || {};
    setState({
      ...INITIAL,
      ...config,
      open: true,
      mode: 'prompt',
      title: config.title || '请输入',
      confirmLabel: config.confirmLabel || '确定',
    });
    setDraft(config.defaultValue || '');
    return new Promise((resolve) => {
      resolverRef.current = resolve;
    });
  }, []);

  const settle = useCallback((result) => {
    setState((previous) => ({ ...previous, open: false }));
    const resolve = resolverRef.current;
    resolverRef.current = null;
    if (resolve) resolve(result);
  }, []);

  const submitPrompt = () => {
    const next = draft.trim();
    if (!next) return;
    settle(next);
  };

  const value = useMemo(() => ({ confirm, prompt }), [confirm, prompt]);

  return (
    <ConfirmContext.Provider value={value}>
      {children}
      {state.open ? (
        <Modal
          title={state.title}
          kicker={state.mode === 'prompt' ? 'INPUT' : 'CONFIRM'}
          size="sm"
          onClose={() => settle(state.mode === 'prompt' ? null : false)}
          footer={
            <div className="ui-modal__actions">
              <Button
                variant="neutral"
                onClick={() => settle(state.mode === 'prompt' ? null : false)}
              >
                取消
              </Button>
              <Button
                variant={state.tone === 'danger' ? 'danger' : 'primary'}
                disabled={state.mode === 'prompt' && !draft.trim()}
                onClick={() => (state.mode === 'prompt' ? submitPrompt() : settle(true))}
              >
                {state.confirmLabel}
              </Button>
            </div>
          }
        >
          {state.mode === 'prompt' ? (
            <div className="ui-prompt">
              {state.message ? <p className="ui-prompt__message">{state.message}</p> : null}
              <input
                className="ui-input"
                value={draft}
                autoFocus
                placeholder={state.placeholder}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') submitPrompt();
                }}
              />
            </div>
          ) : (
            <div className="ui-confirm">
              <span
                className={`ui-confirm__icon${state.tone === 'danger' ? ' is-danger' : ''}`}
                aria-hidden="true"
              >
                <CircleAlert size={20} />
              </span>
              <p className="ui-confirm__message">{state.message}</p>
            </div>
          )}
        </Modal>
      ) : null}
    </ConfirmContext.Provider>
  );
}

export function useConfirm() {
  const context = useContext(ConfirmContext);
  if (!context) {
    return {
      confirm: async () => window.confirm('确认执行该操作？'),
      prompt: async (options) => window.prompt(options?.message || '请输入', options?.defaultValue || ''),
    };
  }
  return context;
}
