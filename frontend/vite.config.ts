import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/static/canvas-app/",
  plugins: [react()],
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
});
