/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        merek: { 50: "#eef6ff", 100: "#d9eaff", 500: "#1f6fd1", 600: "#1559b0", 700: "#0f4589", 900: "#0b2a52" },
      },
    },
  },
  plugins: [],
};
