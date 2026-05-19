import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        "cta-red": "#c60c30",
        "cta-blue": "#00a1de",
      },
    },
  },
  plugins: [],
};

export default config;
