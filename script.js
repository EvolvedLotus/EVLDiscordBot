// API Configuration - Supports both development and production
function getApiBaseUrl() {
    const hostname = window.location.hostname;

    // Production: GitHub Pages
    if (hostname === 'evolvedlotus.github.io') {
        return 'https://your-railway-app.railway.app'; // Replace with your actual Railway app URL
    }

    // Local development: Try common ports
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
        // Try to detect if backend is running on port 5000 (Flask default)
        // If not available, fallback to port 3000
        return 'http://localhost:5000';
    }

    // Railway/Netlify deployment
    if (window.API_BASE_URL) {
        return window.API_BASE_URL;
    }

    // Fallback
    return 'http://localhost:5000';
}

const API_BASE_URL = getApiBaseUrl();

// Helper function to make API calls with proper CORS support
async function apiCall(endpoint, options = {}) {
    try {
        // Default options with CORS support
        const defaultOptions = {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
            },
            credentials: 'include',
            mode: 'cors'
        };

        // Merge options
        const fetchOptions = { ...defaultOptions, ...options };

        // Make request
        const response = await fetch(`${API_BASE_URL}${endpoint}`, fetchOptions);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        return data;
    } catch (error) {
        console.error(`API Error (${endpoint}):`, error);
        throw error;
    }
}
