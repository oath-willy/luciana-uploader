import React, { useState } from "react";
import { GridColDef } from "@mui/x-data-grid";
import { Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Stack, Typography } from "@mui/material";

const stages: Record<string, string> = {
  queued: "In coda", retrieving: "Ricerca nel PDB", classifying: "Classificazione IA",
  refining: "Ricerca di altri precedenti", reviewing: "Revisione IA", completed: "Completato", failed: "Errore",
};
const confidence: Record<string, string> = { high: "Alta", medium: "Media", low: "Bassa" };
const outcomes: Record<string, string> = { confirmed: "Confermato", corrected: "Corretto", unresolved: "Da verificare" };

function PacAiEvidence({ row }: { row: Record<string, any> }) {
  const [open, setOpen] = useState(false);
  const result = row.pac_ai_result;
  if (!result) return null;
  return <>
    <Button size="small" onClick={(event) => { event.stopPropagation(); setOpen(true); }}>Dettagli PAC-AI</Button>
    <Dialog open={open} onClose={() => setOpen(false)} maxWidth="md" fullWidth onClick={(event) => event.stopPropagation()}>
      <DialogTitle>PAC-AI · {row.company_item_code}</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <Typography>{row.description}</Typography>
          {result.decision !== "match" && <Alert severity="warning">Proposta da verificare: le evidenze disponibili non consentono una classificazione certa.</Alert>}
          <Typography><strong>Master Code proposto:</strong> {result.master_code || "Non determinato"} · Affidabilità {confidence[result.confidence]?.toLowerCase()}</Typography>
          <Typography>{[result.classification?.family, result.classification?.subfamily, result.classification?.product_group].filter(Boolean).join(" → ")}</Typography>
          <Box><Typography fontWeight={600}>Indicazioni per codifica</Typography><Typography>{result.classification?.mc_desc || "Nessuna nota specifica"}</Typography></Box>
          <Box><Typography fontWeight={600}>Motivazione finale</Typography><Typography>{result.rationale}</Typography></Box>
          <Box><Typography fontWeight={600}>Prima proposta: {result.initial_master_code || "Non determinata"}</Typography><Typography>{result.initial_rationale}</Typography></Box>
          <Box>
            <Typography fontWeight={600}>Precedenti PDB utilizzati</Typography>
            {result.evidence?.length ? result.evidence.map((entry: Record<string, any>) =>
              <Box key={entry.pdb_ref} sx={{ mt: 1, p: 1, border: "1px solid", borderColor: "divider", borderRadius: 1 }}>
                <Typography fontWeight={600}>{entry.pdb_ref} · {entry.master_code}</Typography>
                <Typography>{entry.description}</Typography>
                <Typography variant="body2" color="text.secondary">{[entry.brand, entry.father_name, entry.pack, entry.feature, entry.measure].filter(Boolean).join(" · ")}</Typography>
              </Box>) : <Typography>Nessun precedente specifico citato. Consultare la motivazione e le note della classificazione.</Typography>}
          </Box>
          <Typography variant="caption" color="text.secondary">La proposta PAC-AI non modifica la codifica salvata. L’affidabilità è una valutazione qualitativa.</Typography>
        </Stack>
      </DialogContent>
      <DialogActions><Button onClick={() => setOpen(false)}>Chiudi</Button></DialogActions>
    </Dialog>
  </>;
}

export function pacAiColumns(onRetry: (row: Record<string, any>) => void): GridColDef[] {
  return [
    {
      field: "pac_ai_status", headerName: "PAC-AI", width: 240, sortable: false, filterable: false,
      renderCell: ({ row }) => <Stack spacing={0.5} sx={{ py: 1, whiteSpace: "normal", width: "100%" }}>
        <Typography variant="body2">{row.pac_ai_status ? stages[row.pac_ai_stage] || stages[row.pac_ai_status] || "In elaborazione" : "—"}</Typography>
        {row.pac_ai_error_message && <Typography variant="caption" color="error">{row.pac_ai_error_message}</Typography>}
        {row.pac_ai_status === "failed" && <Button size="small" onClick={(event) => { event.stopPropagation(); onRetry(row); }}>Riprova PAC-AI</Button>}
        {row.pac_ai_result && <Chip size="small" sx={{ alignSelf: "flex-start" }}
          color={row.pac_ai_result.decision === "match" ? "success" : "warning"}
          label={outcomes[row.pac_ai_result.review_outcome] || "Da verificare"} />}
      </Stack>,
    },
    {
      field: "pac_ai_master_code", headerName: "Master Code PAC-AI", width: 205, sortable: false, filterable: false,
      renderCell: ({ row }) => <Stack spacing={0.5} sx={{ py: 1 }}>
        <Typography fontWeight={600}>{row.pac_ai_result?.master_code || "—"}</Typography>
        {row.pac_ai_result && <Typography variant="caption">Affidabilità: {confidence[row.pac_ai_result.confidence]}</Typography>}
      </Stack>,
    },
    {
      field: "pac_ai_classification", headerName: "Classificazione PAC-AI", width: 310, sortable: false, filterable: false,
      renderCell: ({ row }) => <Typography variant="body2" sx={{ whiteSpace: "normal", py: 1 }}>
        {[row.pac_ai_result?.classification?.family, row.pac_ai_result?.classification?.subfamily, row.pac_ai_result?.classification?.product_group].filter(Boolean).join(" → ") || "—"}
      </Typography>,
    },
    {
      field: "pac_ai_rationale", headerName: "Motivazione PAC-AI", width: 430, sortable: false, filterable: false,
      renderCell: ({ row }) => <Stack sx={{ whiteSpace: "normal", py: 1, alignItems: "flex-start" }}>
        <Typography variant="body2">{row.pac_ai_result?.rationale || "—"}</Typography>
        <PacAiEvidence row={row} />
      </Stack>,
    },
  ];
}
