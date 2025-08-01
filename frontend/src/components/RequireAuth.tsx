import { useEffect, useState, ReactNode } from "react";
import { useNavigate } from "react-router-dom";

export function RequireAuth({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [authorized, setAuthorized] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const isLocal = window.location.hostname === "localhost";

    if (isLocal) {
      console.log("🧪 Bypass autenticazione in locale");
      setAuthorized(true);
      setLoading(false);
      return;
    }

    fetch("/.auth/me")
      .then((res) => res.json())
      .then((data) => {
        const user = data.clientPrincipal;
        if (!user) {
          navigate("/login");
          return;
        }

        const email = user.userDetails || "";
        if (
          email.endsWith("@key-stone.it") ||
          email.toLowerCase() === "matteo@finstat.it"
        ) {
          setAuthorized(true);
        } else {
          alert("Accesso negato: solo utenti interni @key-stone.it sono autorizzati.");
          window.location.href = "https://www.microsoft.com";
        }
      })
      .finally(() => setLoading(false));
  }, [navigate]);

  if (loading) return <p>🔄 Verifica accesso...</p>;
  return authorized ? <>{children}</> : null;
}
