import {
  BookOpen,
  Bot,
  Home,
  Image as ImageIcon,
  Plug,
  ScrollText,
  Sparkles,
  UsersRound,
} from 'lucide-react';

/** 侧边栏导航定义：id 同时作为页面 key 与顶栏标题来源。 */
export const NAV_ITEMS = [
  {
    id: 'overview',
    label: '运行总览',
    hint: '节点与服务状态',
    icon: Home,
    tone: 'indigo',
    group: 'main',
  },
  {
    id: 'accounts',
    label: '平台账号',
    hint: 'Bot 与账号策略',
    icon: Bot,
    tone: 'indigo',
    group: 'main',
  },
  {
    id: 'personas',
    label: '人格提示',
    hint: '人格模板工作台',
    icon: Sparkles,
    tone: 'blossom',
    group: 'main',
  },
  {
    id: 'groups',
    label: '群聊策略',
    hint: '群级策略覆盖',
    icon: UsersRound,
    tone: 'mint',
    group: 'main',
  },
  {
    id: 'interfaces',
    label: '接口能力',
    hint: '模型与工具目录',
    icon: Plug,
    tone: 'amber',
    group: 'main',
  },
  {
    id: 'memory',
    label: '记忆管理',
    hint: '全局 Memory 与黑话',
    icon: BookOpen,
    tone: 'indigo',
    group: 'data',
  },
  {
    id: 'memes',
    label: '表情包',
    hint: '表情包库与工具',
    icon: ImageIcon,
    tone: 'blossom',
    group: 'data',
  },
  {
    id: 'logs',
    label: '对话日志',
    hint: '消息与用量记录',
    icon: ScrollText,
    tone: 'mint',
    group: 'data',
  },
];

export const NAV_GROUPS = [
  { id: 'main', label: '工作台' },
  { id: 'data', label: '数据与记录' },
];

export function findNavItem(page) {
  return NAV_ITEMS.find((item) => item.id === page) || NAV_ITEMS[0];
}
