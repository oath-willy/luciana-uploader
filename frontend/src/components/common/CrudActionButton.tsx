import { Button, ButtonProps } from "@mui/material";
import { Plus, Save, Trash2 } from "lucide-react";

type CrudAction = "add" | "delete" | "save";

type CrudActionButtonProps = Omit<ButtonProps, "startIcon" | "action"> & {
  crudAction: CrudAction;
  label?: string;
};

const actionConfig = {
  add: {
    label: "Aggiungi",
    icon: Plus,
    color: "primary" as const,
    variant: "contained" as const,
  },
  delete: {
    label: "Elimina",
    icon: Trash2,
    color: "error" as const,
    variant: "outlined" as const,
  },
  save: {
    label: "Salva",
    icon: Save,
    color: "primary" as const,
    variant: "contained" as const,
  },
};

export default function CrudActionButton({
  crudAction,
  label,
  children,
  ...buttonProps
}: CrudActionButtonProps) {
  const config = actionConfig[crudAction];
  const Icon = config.icon;

  return (
    <Button
      color={config.color}
      variant={config.variant}
      startIcon={<Icon size={16} />}
      {...buttonProps}
    >
      {children || label || config.label}
    </Button>
  );
}
