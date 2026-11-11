import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import './Modal.css';

const FOCUSABLE =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * 浮层面板：遮罩淡入 + 面板上浮缩放入场，支持 Esc 关闭、点击遮罩关闭、
 * 打开期间锁定背景滚动，并把焦点收束在面板内。
 */
export default function Modal({
  title,
  kicker = 'CONFIGURATION',
  size = 'md',
  onClose,
  children,
  footer,
}) {
  const panelRef = useRef(null);
  const restoreFocusRef = useRef(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    restoreFocusRef.current = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const panel = panelRef.current;
    const preferred =
      panel?.querySelector('input:not([disabled]), textarea:not([disabled]), select:not([disabled])') ||
      panel?.querySelector(FOCUSABLE);
    if (preferred instanceof HTMLElement) {
      preferred.focus({ preventScroll: true });
    } else if (panel instanceof HTMLElement) {
      panel.focus({ preventScroll: true });
    }

    const onKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (event.key !== 'Tab' || !panel) return;
      const nodes = [...panel.querySelectorAll(FOCUSABLE)].filter(
        (node) => node.offsetParent !== null || node === document.activeElement,
      );
      if (!nodes.length) return;
      const firstNode = nodes[0];
      const lastNode = nodes[nodes.length - 1];
      if (event.shiftKey && document.activeElement === firstNode) {
        event.preventDefault();
        lastNode.focus();
      } else if (!event.shiftKey && document.activeElement === lastNode) {
        event.preventDefault();
        firstNode.focus();
      }
    };

    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.body.style.overflow = previousOverflow;
      const restore = restoreFocusRef.current;
      if (restore instanceof HTMLElement && document.contains(restore)) {
        restore.focus({ preventScroll: true });
      }
    };
  }, []);

  return createPortal(
    <div
      className="ui-modal"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={panelRef}
        className={`ui-modal__panel ui-modal__panel--${size}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
      >
        <header className="ui-modal__head">
          <div>
            <span className="kicker">{kicker}</span>
            <h2 className="ui-modal__title">{title}</h2>
          </div>
          <button type="button" className="ui-modal__close" onClick={onClose} aria-label="关闭">
            <X size={18} />
          </button>
        </header>
        <div className="ui-modal__body">{children}</div>
        {footer ? <footer className="ui-modal__footer">{footer}</footer> : null}
      </div>
    </div>,
    document.body,
  );
}

/** 浮层底部操作区：取消 + 保存。 */
export function ModalFooter({ onClose, onSave, busy = false, saveLabel = '保存设置' }) {
  return (
    <div className="ui-modal__actions">
      <button type="button" className="ui-button ui-button--neutral ui-button--md" onClick={onClose} disabled={busy}>
        取消
      </button>
      <button
        type="button"
        className="ui-button ui-button--primary ui-button--md"
        onClick={onSave}
        disabled={busy}
        aria-busy={busy || undefined}
      >
        {busy ? <span className="ui-button__spinner" aria-hidden="true" /> : null}
        <span>{busy ? '保存中…' : saveLabel}</span>
      </button>
    </div>
  );
}
