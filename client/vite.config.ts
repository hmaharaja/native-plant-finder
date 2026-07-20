import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: process.env.VITE_BASE_PATH ?? "/native-plant-finder/",
  plugins: [react()],
  build: {
    sourcemap: true
  },
  server: {
    port: 5173
  }
});
