import { Box, CircularProgress, LinearProgress, Stack, Typography } from "@mui/material";

export default function ClassifierProgress({ label, name, detail }: { label: string; name: string; detail?: string }) {
  return <Stack spacing={0.5} sx={{ width: "100%", minWidth: 0, py: 1 }}>
    <Box sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0 }}>
      <CircularProgress size={16} color="warning" sx={{ flexShrink: 0 }} aria-label={`${name} in elaborazione`} />
      <Typography variant="body2" noWrap>{label}</Typography>
    </Box>
    <LinearProgress color="warning" aria-label={`Avanzamento ${name}`} />
    {detail && <Typography variant="caption" color="warning.dark">{detail}</Typography>}
  </Stack>;
}
