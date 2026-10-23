/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{vue,js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#17211d",
        paper: "#f6f7f4",
        line: "#d9ddd8",
        accent: "#0f766e",
        "accent-dark": "#115e59",
        "soft-blue": "#e8eff8",
      },
      boxShadow: { panel: "0 12px 34px rgba(23, 33, 29, 0.08)" },
    },
  },
  plugins: [],
}
