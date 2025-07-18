import { useEffect, useState } from "react";

export default function AuthDebug() {
  const [user, setUser] = useState<any>(null);

  useEffect(() => {
    fetch("/.auth/me")
      .then((res) => res.json())
      .then((data) => {
        setUser(data.clientPrincipal);
      });
  }, []);

  if (!user) return <p>⏳ Non sei autenticato</p>;

  return (
    <div style={{ padding: "2rem" }}>
      <h2>👤 Sei autenticato</h2>
      <pre>{JSON.stringify(user, null, 2)}</pre>
      <a href="/.auth/logout">🔓 Logout</a>
    </div>
  );
}
