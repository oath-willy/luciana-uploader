import { useEffect, useState } from "react";

export default function Login() {
  const [redirecting, setRedirecting] = useState(true);

  useEffect(() => {
    console.log("Redirecting to Azure Entra ID...");
    try {
      window.location.href = "/.auth/login/aad";
    } catch (err) {
      console.error("Errore nel redirect:", err);
      setRedirecting(false);
    }
  }, []);

  return (
    <div style={{ padding: "2rem" }}>
      {redirecting ? (
        <p>Reindirizzamento al login EntraID...</p>
      ) : (
        <p>Errore durante il reindirizzamento. Prova <a href="/.auth/login/aad">questo link</a>.</p>
      )}
    </div>
  );
}
