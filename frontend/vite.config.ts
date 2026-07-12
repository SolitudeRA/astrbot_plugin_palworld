import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// 产物硬约束：单 JS + 单 CSS，零跨-chunk import、零 import()
export default defineConfig({
  plugins: [vue()],
  base: './', // asset_token 重写要求相对路径
  build: {
    outDir: fileURLToPath(new URL('../pages/settings', import.meta.url)),
    emptyOutDir: true,
    cssCodeSplit: false,
    sourcemap: false,
    rollupOptions: {
      output: {
        inlineDynamicImports: true, // 内联动态 import → 零 import()/零异步 chunk
        manualChunks: undefined,
        entryFileNames: 'assets/index.js',
        chunkFileNames: 'assets/index.js',
        assetFileNames: 'assets/[name][extname]',
      },
    },
  },
})
