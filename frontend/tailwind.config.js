export default {
    content: [
        "./index.html",
        "./src/**/*.{js,jsx}",
    ],
    theme: {
        extend: {
            colors: {
                brand: {
                    primary: "#00703C",
                    secondary: "#116DFF",
                    accent: "#48bb78",
                    warning: "#ed8936",
                    danger: "#e53e3e",
                    background: "#FFFFFF",
                    surface: "#F4F4F4",
                    text_primary: "#2F2B36",
                    text_secondary: "#000000"
                }
            },
            fontFamily: {
                sans: ['"Wix Madefor Text"', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
                display: ['"Wix Madefor Display"', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
            },
            boxShadow: {
                'glass': '0 8px 32px 0 rgba(0, 0, 0, 0.05)',
                'premium': '0 10px 40px -10px rgba(0, 112, 60, 0.1)',
                'card': '0 2px 4px 0 rgba(0, 0, 0, 0.02), 0 1px 2px 0 rgba(0, 0, 0, 0.01)'
            }
        },
    },
    plugins: [],
}
