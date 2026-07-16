import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: "#eeeae3",
        canvas: "#141310",
        panel: "#1c1b18",
        line: "#37342e",
        moss: "#78a681",
        lime: "#3b2822",
        ember: "#e27760",
        clay: "#d97757",
        sand: "#25231f",
        muted: "#a8a198",
        deep: "#0f0f0d",
      },
      boxShadow: {
        panel:
          "0 1px 1px rgba(0, 0, 0, 0.35), 0 16px 42px rgba(0, 0, 0, 0.18)",
      },
    },
  },
  plugins: [],
};

export default config;
