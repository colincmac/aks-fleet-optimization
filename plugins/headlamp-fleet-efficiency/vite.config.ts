import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig(({ command, mode }) => ({
  publicDir: command === 'serve' || mode === 'preview' ? 'preview-public' : false,
  plugins: [react()],
  test: { environment: 'jsdom', include: ['test/**/*.test.{ts,tsx}'], restoreMocks: true },
}));
