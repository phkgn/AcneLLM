import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: "#18201d",
        canvas: "#f4f1e9",
        panel: "#fffdf7",
        line: "#ddd8ca",
        moss: "#28624a",
        lime: "#cde76c",
        ember: "#b34f35",
      },
      boxShadow: {
        panel: "0 18px 60px rgba(24, 32, 29, 0.08)",
      },
    },
  },
  plugins: [],
};

export default config;
