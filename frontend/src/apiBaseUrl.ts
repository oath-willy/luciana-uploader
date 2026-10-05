// In Azure, the linked SWA gateway authenticates every browser API request.
export const backendUrl = ['localhost', '127.0.0.1'].includes(window.location.hostname)
  ? process.env.REACT_APP_BACKEND_URL || '' : '';
