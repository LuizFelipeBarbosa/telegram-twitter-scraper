var _a;
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";
var proxyTarget = (_a = process.env.VIZ_API_PROXY_TARGET) !== null && _a !== void 0 ? _a : "http://localhost:8000";
export default defineConfig({
    plugins: [react()],
    server: {
        host: "0.0.0.0",
        port: 5173,
        proxy: {
            "/api": proxyTarget,
        },
    },
    test: {
        environment: "jsdom",
        globals: true,
        setupFiles: "./src/test/setup.ts",
    },
});
