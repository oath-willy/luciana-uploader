const colors = {
  bs25: { main: "#1565c0", pale: "#e3f2fd", border: "#90caf9" },
  pacAi: { main: "#00695c", pale: "#e0f2f1", border: "#80cbc4" },
};

export function classifierGroupSx(group: keyof typeof colors) {
  const palette = colors[group];
  return {
    display: "inline-flex", alignItems: "center", gap: 0.5, p: 0.5,
    border: "1px solid", borderRadius: 1.5, borderColor: palette.border, bgcolor: palette.pale,
    "& .MuiButton-outlined:not(.Mui-disabled), & .MuiIconButton-root:not(.Mui-disabled)": { color: palette.main, borderColor: palette.border },
    "& .MuiButton-contained:not(.Mui-disabled)": { bgcolor: palette.main, color: "#fff" },
    "& .MuiSwitch-switchBase.Mui-checked": { color: palette.main },
    "& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track": { bgcolor: palette.main },
  };
}

export const classifierGridSx = {
  "& .mc-code-bs25-header": { bgcolor: colors.bs25.pale, color: colors.bs25.main, borderTop: `3px solid ${colors.bs25.main}` },
  "& .mc-code-pac-ai-header": { bgcolor: colors.pacAi.pale, color: colors.pacAi.main, borderTop: `3px solid ${colors.pacAi.main}` },
  "& .mc-code-classifier-cell": { lineHeight: 1.5 },
  "& .mc-code-classifier-cell .MuiTypography-root, & .mc-code-classifier-cell .MuiChip-label, & .mc-code-classifier-cell .MuiButton-root": {
    fontSize: "inherit", lineHeight: 1.5,
  },
  "& .mc-code-classifier-cell .MuiChip-root": { maxWidth: "100%" },
  "& .mc-code-row-compact .mc-code-classifier-cell .MuiTypography-root": {
    whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", minWidth: 0,
  },
  "& .mc-code-row-compact .mc-code-classifier-cell > .MuiStack-root > .MuiStack-root:first-child": {
    flexWrap: "nowrap", overflow: "hidden",
  },
};
