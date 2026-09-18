import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 热更新模式（./start_dev.sh --watch）用的开发服务器端口，以及要转发到的 FastAPI 地址。
// 这两个值写死是有意的：tsconfig.node.json 里没有 @types/node，读不到 process.env，
// 为了一个端口号去加一个类型依赖不划算。如果改过 .env 里的 APP_PORT，把下面一行一起改。
const DEV_PORT = 5174;
const API_TARGET = "http://127.0.0.1:8015";

export default defineConfig(({ command }) => ({
  // 构建产物由 FastAPI 挂在 /static/canvas-app/ 下；开发服务器直接在根路径提供页面，
  // 这样 /workflow/xxx 这类前端路由在热更新模式下也能落回 index.html。
  base: command === "serve" ? "/" : "/static/canvas-app/",
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: DEV_PORT,
    strictPort: true,
    // 页面是同源调用 /api/...，开发时统一转发给本地后端（后端只有 /api 这一个前缀）。
    proxy: { "/api": { target: API_TARGET, changeOrigin: true } },
  },
  build: {
    outDir: "../web/static/canvas-app",
    emptyOutDir: true,
    rollupOptions: {
      output: {
        entryFileNames: "assets/[name]-[hash].js",
        chunkFileNames: "assets/[name]-[hash].js",
        assetFileNames: "assets/[name]-[hash][extname]",
        manualChunks: {
          "canvas-vendor": ["@xyflow/react", "zustand"],
        },
      },
    },
  },
}));
