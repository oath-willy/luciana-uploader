export const COMPACT_LAYOUT_SCALE = 0.65;
const textScale = 0.8 / COMPACT_LAYOUT_SCALE;

export const compactTypographyStyles = {
  fontSize: `${textScale}rem`,
  "& .MuiTypography-h1": { fontSize: `${6 * textScale}rem` },
  "& .MuiTypography-h2": { fontSize: `${3.75 * textScale}rem` },
  "& .MuiTypography-h3": { fontSize: `${3 * textScale}rem` },
  "& .MuiTypography-h4": { fontSize: `${2.125 * textScale}rem` },
  "& .MuiTypography-h5": { fontSize: `${1.5 * textScale}rem` },
  "& .MuiTypography-h6": { fontSize: `${1.25 * textScale}rem` },
  "& .MuiTypography-subtitle1, & .MuiTypography-body1": { fontSize: `${textScale}rem` },
  "& .MuiTypography-subtitle2, & .MuiTypography-body2": { fontSize: `${0.875 * textScale}rem` },
  "& .MuiTypography-caption, & .MuiTypography-overline": { fontSize: `${0.75 * textScale}rem` },
  "& .MuiButton-root, & .MuiToggleButton-root": { fontSize: `${0.875 * textScale}rem` },
  "& .MuiInputBase-root, & .MuiInputLabel-root": { fontSize: `${textScale}rem` },
  "& .MuiChip-label": { fontSize: `${0.8125 * textScale}rem` },
  "& .MuiAlert-message, & .MuiDataGrid-root, & .MuiTablePagination-root": { fontSize: `${0.875 * textScale}rem` },
} as const;
