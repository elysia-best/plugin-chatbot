/** 展示层格式化与领域字段读取的纯函数集合。 */

export function formatTime(value) {
  if (!value) return '刚刚';
  return new Date(value * 1000).toLocaleString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function formatBytes(bytes) {
  const size = Number(bytes) || 0;
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatCost(value) {
  return `$${Number(value || 0).toFixed(4)}`;
}

export function modelId(model) {
  if (typeof model === 'string') return model;
  return model?.id || '';
}

export function modelContext(model) {
  return typeof model === 'object' && model ? model.context_length : null;
}

export function providerLabel(provider) {
  if (!provider) return '';
  return provider.name || provider.base_url || provider.id || '未命名接口';
}

export function conversationLabel(row) {
  const scope = row?.kind === 'group' ? '群聊' : '私聊';
  return `${scope} · ${row?.name || row?.peer_id || '未知会话'}`;
}

export function conversationStatus(status) {
  if (status === 'pending') return '待确认';
  if (status === 'rejected') return '已拒绝';
  return '已确认';
}

export function messageText(content) {
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) {
    return content
      .map((item) => item?.text || item?.content || `[${item?.type || '内容'}]`)
      .join('');
  }
  return content ? JSON.stringify(content) : '';
}

export function messageRoleLabel(role) {
  if (role === 'user') return '用户';
  if (role === 'assistant') return 'Agent';
  if (role === 'tool') return '工具';
  return role || '消息';
}

export function memorySlug(title) {
  return (
    String(title || '')
      .toLowerCase()
      .normalize('NFKD')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-|-$/g, '')
      .slice(0, 64) || `memory-${Date.now()}`
  );
}
