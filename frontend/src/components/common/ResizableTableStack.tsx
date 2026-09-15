import { ReactNode, useRef, useState } from "react";
import { Box } from "@mui/material";
import { GripHorizontal } from "lucide-react";

const MIN_SPLIT = 20;
const MAX_SPLIT = 80;
const clamp = (value: number) => Math.min(MAX_SPLIT, Math.max(MIN_SPLIT, value));

export default function ResizableTableStack({ top, bottom }: { top: ReactNode; bottom?: ReactNode }) {
  const container = useRef<HTMLDivElement>(null);
  const drag = useRef<{ pointerId: number; startY: number; startSplit: number; height: number } | null>(null);
  const [split, setSplit] = useState(50);
  const [dragging, setDragging] = useState(false);

  const finishDrag = () => {
    drag.current = null;
    setDragging(false);
  };

  return (
    <Box ref={container} sx={{ minHeight: 0, minWidth: 0, height: "100%", display: "grid",
      gridTemplateRows: bottom ? `minmax(0, ${split}fr) 20px minmax(0, ${100 - split}fr)` : "minmax(0, 1fr)",
      userSelect: dragging ? "none" : undefined,
    }}>
      <Box sx={{ minHeight: 0, minWidth: 0 }}>{top}</Box>
      {bottom && <Box role="separator" tabIndex={0} aria-label="Ridimensiona le tabelle"
        aria-orientation="horizontal" aria-valuemin={MIN_SPLIT} aria-valuemax={MAX_SPLIT}
        aria-valuenow={Math.round(split)} aria-valuetext={`${Math.round(split)}% tabella superiore`}
        onPointerDown={(event) => {
          if (event.button !== 0 || !container.current) return;
          event.preventDefault();
          event.currentTarget.focus();
          event.currentTarget.setPointerCapture(event.pointerId);
          const height = container.current.getBoundingClientRect().height - event.currentTarget.getBoundingClientRect().height;
          drag.current = { pointerId: event.pointerId, startY: event.clientY, startSplit: split, height: Math.max(1, height) };
          setDragging(true);
        }}
        onPointerMove={(event) => {
          const current = drag.current;
          if (current?.pointerId === event.pointerId) {
            setSplit(clamp(current.startSplit + (event.clientY - current.startY) / current.height * 100));
          }
        }}
        onPointerUp={(event) => {
          if (drag.current?.pointerId !== event.pointerId) return;
          event.currentTarget.releasePointerCapture(event.pointerId);
          finishDrag();
        }}
        onPointerCancel={finishDrag} onLostPointerCapture={finishDrag}
        onDoubleClick={() => setSplit(50)}
        onKeyDown={(event) => {
          if (!["ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
          event.preventDefault();
          setSplit((value) => event.key === "Home" ? MIN_SPLIT : event.key === "End" ? MAX_SPLIT
            : clamp(value + (event.key === "ArrowDown" ? 2 : -2)));
        }}
        sx={{ cursor: "row-resize", touchAction: "none", display: "flex", alignItems: "center",
          justifyContent: "center", color: "text.secondary", position: "relative",
          backgroundColor: dragging ? "action.selected" : "transparent",
          "&::before": { content: '""', position: "absolute", left: 0, right: 0, borderTop: "1px solid", borderColor: "divider" },
          "&:hover": { backgroundColor: "action.hover" },
          "&:focus-visible": { outline: "2px solid", outlineColor: "primary.main", outlineOffset: -2 },
        }}>
        <GripHorizontal size={20} aria-hidden="true" style={{ position: "relative", background: "inherit" }} />
      </Box>}
      {bottom && <Box sx={{ minHeight: 0, minWidth: 0 }}>{bottom}</Box>}
    </Box>
  );
}
