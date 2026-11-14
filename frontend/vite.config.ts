import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    host: true, // takım arkadaşları ağ üzerinden açabilsin
  },
  build: {
    chunkSizeWarningLimit: 1000, // Recharts büyük; offline tek paket sorun değil
  },
});
