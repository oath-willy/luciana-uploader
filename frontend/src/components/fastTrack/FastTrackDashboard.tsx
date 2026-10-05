import { useEffect, useState } from "react";
import { Alert, Box, Loader } from "@mantine/core";
import { Link } from "react-router-dom";
import { DashboardKey, FastTrackStatus, fastTrackBaseUrl, readFastTrackStatus } from "./fastTrackApi";
import layout from "./FastTrackLayout.module.css";

export default function FastTrackDashboard({ dashboard }: { dashboard: DashboardKey }) {
  const [status, setStatus] = useState<FastTrackStatus | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let disposed = false;
    setLoading(true);
    readFastTrackStatus().then(value => { if (!disposed) { setStatus(value); setError(""); } })
      .catch(e => { if (!disposed) setError(e.message); }).finally(() => { if (!disposed) setLoading(false); });
    return () => { disposed = true; };
  }, [dashboard]);
  const current = status?.dashboards[dashboard];
  const title = dashboard === "gold" ? "Gold monitoring" : "Fast Track Forecast";
  return <Box className={layout.dashboard}>
    {error && <Alert color="red" mb="sm">{error}</Alert>}
    {loading && !status && <Loader aria-label="Caricamento dashboard" />}
    {!loading && status && !current?.url && <Alert color="blue">La dashboard non è ancora pubblicata.
      Recupera i sorgenti e avvia l’aggiornamento dei dati da <Link to="/fast-track/dashboard/settings">Fast Track Settings</Link>.</Alert>}
    {current?.url && <iframe key={current.url} src={`${fastTrackBaseUrl}${current.url}`} title={title}
      sandbox="allow-scripts allow-same-origin allow-downloads" referrerPolicy="same-origin"
      className={layout.frame} />}
  </Box>;
}
