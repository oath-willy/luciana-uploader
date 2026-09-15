import { Box, Typography } from "@mui/material";
import { useState } from "react";
import DatasetTable, { ReferenceSelection } from "./itemsCode/DatasetTable";
import { COMPACT_LAYOUT_SCALE, compactTypographyStyles } from "./common/compactWorkspace";
import ResizableTableStack from "./common/ResizableTableStack";

export default function ItemsCode() {
  const [referenceSelection, setReferenceSelection] = useState<ReferenceSelection | null>(null);
  const [referenceVisible, setReferenceVisible] = useState(false);
  const top = <DatasetTable dataset="new-items" title="PDB New Items" requireCompany
    referenceSelection={referenceSelection} referenceVisible={referenceVisible}
    onReferenceVisibleChange={(visible) => { setReferenceSelection(null); setReferenceVisible(visible); }} />;
  return (
    <Box sx={{ height: "calc(100dvh - 16px)", width: "100%", minWidth: 0, overflow: "auto" }}>
      <Box sx={{
        ...compactTypographyStyles, zoom: COMPACT_LAYOUT_SCALE,
        width: "100%",
        height: `calc((100dvh - 16px) / ${COMPACT_LAYOUT_SCALE})`,
        minHeight: 700, minWidth: 0, display: "grid",
        gridTemplateRows: "32px minmax(0, 1fr)", gap: 2,
      }}>
        <Typography component="h1" variant="h6">items-code</Typography>
        <ResizableTableStack top={top} bottom={referenceVisible
          ? <DatasetTable dataset="pdb" title="Reference PDB" requireCompany onReferenceSelection={setReferenceSelection} /> : undefined} />
      </Box>
    </Box>
  );
}
