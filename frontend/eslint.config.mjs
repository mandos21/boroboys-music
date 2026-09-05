import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "*.config.ts", "*.tsbuildinfo"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
);
