// src/msalConfig.js
export const msalConfig = {
  auth: {
    // Application (client) ID dell’app registrata in Entra ID
    clientId: "56998f02-856b-495e-8778-884036e74381",

    // Issuer del tuo tenant (single-tenant)
    authority: "https://login.microsoftonline.com/3630ff06-11ea-4763-960a-fc74e8780220",

    // Lascia “/” → Static Web Apps aggiunge in automatico il dominio
    redirectUri: "https://mango-ocean-06166b203.6.azurestaticapps.net/*"
  },
  cache: { cacheLocation: "sessionStorage" }   // default ok
};
