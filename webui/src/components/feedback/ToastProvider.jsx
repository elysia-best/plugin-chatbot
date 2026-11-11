import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { CircleAlert, CircleCheck, Info } from 'lucide-react';
import './ToastProvider.css';

const ToastContext = createContext(null);

const ICONS = {
  success: CircleCheck,
  error: CircleAlert,
  info: Info,
};

/** 轻量提示层：保存成功 / 请求失败等结果反馈。 */
export function ToastProvider({ children }) {
  const [items, setItems] = useState([]);
  const counterRef = useRef(0);
  const timersRef = useRef(new Map());

  useEffect(
    () => () => {
      timersRef.current.forEach((timer) => clearTimeout(timer));
      timersRef.current.clear();
    },
    [],
  );

  const remove = useCallback((id) => {
    setItems((previous) => previous.map((item) => (item.id === id ? { ...item, leaving: true } : item)));
    const timer = setTimeout(() => {
      setItems((previous) => previous.filter((item) => item.id !== id));
      timersRef.current.delete(id);
    }, 220);
    timersRef.current.set(`exit-${id}`, timer);
  }, []);

  const push = useCallback(
    (message, tone = 'info', ttl = 3600) => {
      if (!message) return;
      counterRef.current += 1;
      const id = counterRef.current;
      setItems((previous) => [...previous.slice(-3), { id, message, tone }]);
      const timer = setTimeout(() => remove(id), ttl);
      timersRef.current.set(id, timer);
    },
    [remove],
  );

  const value = useMemo(
    () => ({
      push,
      success: (message) => push(message, 'success'),
      error: (message) => push(message, 'error', 4600),
      info: (message) => push(message, 'info'),
    }),
    [push],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      {createPortal(
        <div className="ui-toasts" role="status" aria-live="polite">
          {items.map((item) => {
            const Icon = ICONS[item.tone] || ICONS.info;
            return (
              <div
                key={item.id}
                className={`ui-toast ui-toast--${item.tone}${item.leaving ? ' is-leaving' : ''}`}
              >
                <span className="ui-toast__icon" aria-hidden="true">
                  <Icon size={17} />
                </span>
                <span className="ui-toast__message">{item.message}</span>
                <button
                  type="button"
                  className="ui-toast__close"
                  onClick={() => remove(item.id)}
                  aria-label="关闭提示"
                >
                  ×
                </button>
              </div>
            );
          })}
        </div>,
        document.body,
      )}
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    return { push: () => {}, success: () => {}, error: () => {}, info: () => {} };
  }
  return context;
}
