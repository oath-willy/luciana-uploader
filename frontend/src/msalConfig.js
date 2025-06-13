// src/msalConfig.js
export const msalConfig = {
  auth: {
    clientId: "95622910-72b1-4eeb-98ea-fa20efbc5673",               // Application (client) ID
    authority:
      "https://login.microsoftonline.com/3630ff06-11ea-4763-960a-fc74e8780220", // Tenant ID
    redirectUri: "https://mango-ocean-06166b203.6.azurestaticapps.net/"
  },
  cache: { cacheLocation: "sessionStorage" }
};
