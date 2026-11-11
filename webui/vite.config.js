import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// 开发时把 /chat-agent 转发到本地 NoneBot 服务（默认 8080），
// 这样 `npm run dev` 可以直接使用真实接口调试，无需每次构建。
const backend = process.env.CHATBOT_BACKEND || 'http://127.0.0.1:8080';

export default defineConfig({
  plugins: [react()],
  base: './',
  build: { outDir: 'dist', emptyOutDir: true },
  server: {
    port: 5178,
    strictPort: false,
    proxy: {
      '/chat-agent': { target: backend, changeOrigin: true },
    },
  },
});
