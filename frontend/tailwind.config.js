/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'premiere-dark': '#1E1E1E',
        'premiere-gray': '#2D2D2D',
        'premiere-light': '#3D3D3D',
        'premiere-accent': '#00A8E8',
      },
      fontFamily: {
        'sans': ['Inter', 'system-ui', 'sans-serif'],
      }
    },
  },
  plugins: [],
}
