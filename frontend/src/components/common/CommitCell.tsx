import { useEffect, useState } from "react";
import { TextField, Tooltip } from "@mui/material";

export default function CommitCell({ value, label, disabled, onCommit }: {
  value: unknown; label: string; disabled?: boolean;
  onCommit: (value: string, applyToMany: boolean) => Promise<void>;
}) {
  const text = String(value ?? "");
  const [draft, setDraft] = useState(text);
  const [error, setError] = useState("");
  useEffect(() => { setDraft(text); setError(""); }, [text]);
  return <Tooltip title={error}>
    <TextField variant="standard" size="small" fullWidth value={draft} error={Boolean(error)}
      slotProps={{ htmlInput: { "aria-label": label, readOnly: disabled, "aria-busy": disabled }, input: { disableUnderline: true } }}
      sx={{ "& input": { fontSize: 13, px: 0.5 }, "&:focus-within": { outline: "1px solid", outlineColor: "primary.main" } }}
      onClick={(event) => event.stopPropagation()}
      onChange={(event) => { setDraft(event.target.value); setError(""); }}
      onBlur={() => { setDraft(text); setError(""); }}
      onKeyDown={async (event) => {
        event.stopPropagation();
        if (event.key === "Escape") { setDraft(text); setError(""); }
        if (event.key !== "Enter" || event.nativeEvent.isComposing || disabled) return;
        event.preventDefault();
        try { await onCommit(draft, event.ctrlKey); setError(""); }
        catch (err: any) { setError(err.message || "Salvataggio fallito"); }
      }}
    />
  </Tooltip>;
}
