import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        "brand-purple": "#8b5cf6",
        "brand-white": "#ffffff",
        "brand-black": "#000000",
        brand: {
          purple: "#8b5cf6",
          white: "#ffffff",
          black: "#000000",
          yellow: "#8b5cf6",
          yellowHover: "#8b5cf6",
          yellowLight: "#ffffff",
          dark: "#000000",
          sidebar: "#000000",
          sidebarHover: "#000000",
          surface: "#ffffff",
          card: "#ffffff",
        },
      },
    },
  },
  plugins: [],
};

export default config;
