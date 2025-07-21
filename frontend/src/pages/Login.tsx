import { useEffect } from "react";

export default function Login() {
  useEffect(() => {
    window.location.href = "/.auth/login/aad";
  }, []);

  return <p>🔐 Reindirizzamento al login...</p>;
}
