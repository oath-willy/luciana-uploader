import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  DataGrid,
  GRID_CHECKBOX_SELECTION_COL_DEF,
  GridColDef,
  GridHeaderCheckbox,
  GridPagination,
  GridPaginationModel,
  GridRowParams,
  GridRowSelectionModel,
} from "@mui/x-data-grid";
import {
  Alert,
  Box,
  Button,
  IconButton,
  InputAdornment,
  TextField,
} from "@mui/material";

export type ServerGridFetchParams = {
  page: number;
  pageSize: number;
  search: string;
  filters: Record<string, string>;
};

export type ServerGridResult = {
  rows: any[];
  total: number;
};

type ServerDataGridProps = {
  title: string;
  columns: GridColDef[];
  fetchRows: (params: ServerGridFetchParams) => Promise<ServerGridResult>;
  getRowId?: (row: any) => string | number;
  pageSizeOptions?: number[];
  defaultPageSize?: number;
  filterFields?: string[];
  toolbarLeft?: React.ReactNode;
  toolbarRight?: React.ReactNode;
  refreshToken?: number;
  silentRefresh?: boolean;
  selectionResetToken?: number;
  externalSelection?: { token: number; rows: any[] };
  checkboxSelection?: boolean;
  selectionHeaderAction?: React.ReactNode;
  onSelectionChange?: (ids: Set<number | string>, rows: any[]) => void;
  onQueryChange?: (params: ServerGridFetchParams) => void;
  onRowsChange?: (rows: any[]) => void;
  onRowClick?: (params: GridRowParams) => void;
  rowHeight?: number;
  getRowHeight?: (params: any) => number | "auto" | null | undefined;
  estimatedRowHeight?: number;
  getRowClassName?: (params: any) => string;
  isRowSelectable?: (params: GridRowParams) => boolean;
  height?: string | number;
  emptyMessage?: string;
};

export default function ServerDataGrid({
  title,
  columns,
  fetchRows,
  getRowId,
  pageSizeOptions = [25, 50, 100, 500],
  defaultPageSize = 50,
  filterFields,
  toolbarLeft,
  toolbarRight,
  refreshToken = 0,
  silentRefresh = false,
  selectionResetToken = 0,
  externalSelection,
  checkboxSelection = false,
  selectionHeaderAction,
  onSelectionChange,
  onQueryChange,
  onRowsChange,
  onRowClick,
  rowHeight = 36,
  getRowHeight,
  estimatedRowHeight = 190,
  getRowClassName,
  isRowSelectable,
  height = "89vh",
  emptyMessage = "Nessun dato",
}: ServerDataGridProps) {
  const [rows, setRows] = useState<any[]>([]);
  const [rowCount, setRowCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [columnFilters, setColumnFilters] = useState<Record<string, string>>({});
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [debouncedColumnFilters, setDebouncedColumnFilters] = useState<Record<string, string>>({});
  const [paginationModel, setPaginationModel] = useState<GridPaginationModel>({
    page: 0,
    pageSize: defaultPageSize,
  });
  const [rowSelectionModel, setRowSelectionModel] =
    useState<GridRowSelectionModel>({
      type: "include",
      ids: new Set(),
    });
  const hasLoadedRows = useRef(false);
  const selectionRowsCache = useRef<Map<number | string, any>>(new Map());

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setDebouncedSearch(search.trim());
      setDebouncedColumnFilters(
        Object.fromEntries(
          Object.entries(columnFilters)
            .map(([field, value]) => [field, value.trim()])
            .filter(([, value]) => value)
        )
      );
    }, 450);

    return () => window.clearTimeout(timeout);
  }, [search, columnFilters]);

  const loadRows = useCallback(async () => {
    if (!silentRefresh || !hasLoadedRows.current) {
      setLoading(true);
    }
    setError("");

    try {
      const result = await fetchRows({
        page: paginationModel.page,
        pageSize: paginationModel.pageSize,
        search: debouncedSearch,
        filters: debouncedColumnFilters,
      });

      setRows(result.rows);
      result.rows.forEach((row) => {
        const id = getRowId ? getRowId(row) : row.id;
        selectionRowsCache.current.set(id, row);
      });
      setRowCount(result.total);
      hasLoadedRows.current = true;
      onRowsChange?.(result.rows);
    } catch (err: any) {
      setRows([]);
      setRowCount(0);
      setError(err.message || "Errore caricamento dati");
    } finally {
      setLoading(false);
    }
  }, [
    fetchRows,
    paginationModel,
    debouncedSearch,
    debouncedColumnFilters,
    onRowsChange,
    getRowId,
    silentRefresh,
  ]);

  useEffect(() => {
    loadRows();
  }, [loadRows, refreshToken]);

  useEffect(() => {
    setRowSelectionModel({ type: "include", ids: new Set() });
    selectionRowsCache.current.clear();
  }, [selectionResetToken]);

  useEffect(() => {
    if (!externalSelection) {
      return;
    }
    const ids = new Set<number | string>();
    externalSelection.rows.forEach((row) => {
      const id = getRowId ? getRowId(row) : row.id;
      ids.add(id);
      selectionRowsCache.current.set(id, row);
    });
    setRowSelectionModel({ type: "include", ids });
  }, [externalSelection?.token, externalSelection, getRowId]);

  const selectedIds = useMemo(() => {
    if (rowSelectionModel.type !== "include") {
      return new Set<number | string>();
    }

    return new Set(Array.from(rowSelectionModel.ids) as Array<number | string>);
  }, [rowSelectionModel]);

  useEffect(() => {
    const selectedRows = Array.from(selectedIds)
      .map((id) => selectionRowsCache.current.get(id))
      .filter(Boolean);
    onSelectionChange?.(selectedIds, selectedRows);
  }, [selectedIds, rows, onSelectionChange]);

  useEffect(() => {
    onQueryChange?.({
      page: paginationModel.page,
      pageSize: paginationModel.pageSize,
      search: debouncedSearch,
      filters: debouncedColumnFilters,
    });
  }, [
    paginationModel,
    debouncedSearch,
    debouncedColumnFilters,
    onQueryChange,
  ]);

  const visibleFilterFields = filterFields || columns.map((column) => column.field);
  const hasActiveFilters =
    Boolean(search.trim()) ||
    Object.values(columnFilters).some((value) => value.trim());

  const handleColumnFilterChange = useCallback((field: string, value: string) => {
    setColumnFilters((current) => ({ ...current, [field]: value }));
    setPaginationModel((current) => ({ ...current, page: 0 }));
  }, []);

  const clearColumnFilter = useCallback((field: string) => {
    setColumnFilters((current) => {
      const next = { ...current };
      delete next[field];
      return next;
    });
    setPaginationModel((current) => ({ ...current, page: 0 }));
  }, []);

  const clearAllFilters = () => {
    setSearch("");
    setColumnFilters({});
    setPaginationModel((current) => ({ ...current, page: 0 }));
  };

  const renderedColumns = useMemo(
    () =>
      columns.map((column) => ({
        ...column,
        renderHeader: () => {
          const value = columnFilters[column.field] || "";
          const canFilter = visibleFilterFields.includes(column.field);

          return (
            <Box sx={{ width: "100%", py: 0.5 }}>
              <Box
                sx={{
                  fontSize: 12,
                  fontWeight: 700,
                  lineHeight: 1.1,
                  mb: 0.5,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
                title={column.headerName}
              >
                {column.headerName}
              </Box>
              {canFilter && (
                <TextField
                  value={value}
                  onChange={(event) =>
                    handleColumnFilterChange(column.field, event.target.value)
                  }
                  onClick={(event) => event.stopPropagation()}
                  onKeyDown={(event) => event.stopPropagation()}
                  placeholder="Filtro"
                  size="small"
                  variant="outlined"
                  fullWidth
                  inputProps={{
                    "aria-label": `Filtro ${column.headerName}`,
                    style: { fontSize: 12, padding: "4px 0 4px 6px" },
                  }}
                  InputProps={{
                    sx: { height: 28, fontSize: 12, pr: value ? 0.25 : 0 },
                    endAdornment: value ? (
                      <InputAdornment position="end">
                        <IconButton
                          aria-label={`Svuota filtro ${column.headerName}`}
                          size="small"
                          onClick={(event) => {
                            event.stopPropagation();
                            clearColumnFilter(column.field);
                          }}
                          sx={{ width: 20, height: 20, fontSize: 12 }}
                        >
                          x
                        </IconButton>
                      </InputAdornment>
                    ) : undefined,
                  }}
                />
              )}
            </Box>
          );
        },
      })),
    [
      columns,
      columnFilters,
      visibleFilterFields,
      handleColumnFilterChange,
      clearColumnFilter,
    ]
  );

  const dataGridColumns = useMemo(() => {
    if (!checkboxSelection || !selectionHeaderAction) {
      return renderedColumns;
    }

    const selectionColumn: GridColDef = {
      ...GRID_CHECKBOX_SELECTION_COL_DEF,
      width: 54,
      minWidth: 54,
      maxWidth: 54,
      renderHeader: (params) => (
        <Box
          sx={{
            height: "100%",
            width: "100%",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "space-evenly",
            py: 0.25,
          }}
        >
          {selectionHeaderAction}
          <GridHeaderCheckbox {...params} />
        </Box>
      ),
    };

    return [selectionColumn, ...renderedColumns];
  }, [checkboxSelection, renderedColumns, selectionHeaderAction]);

  return (
    <Box
      sx={{
        height,
        width: "100%",
        minHeight: 0,
        minWidth: 0,
        maxWidth: "100%",
        overflow: "hidden",
        p: 0,
        display: "flex",
        flexDirection: "column",
      }}
    >
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 1.5,
          mb: 1,
          flexWrap: "wrap",
        }}
      >
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            gap: 1.5,
            flex: "1 1 640px",
            minWidth: 0,
            maxWidth: "100%",
            flexWrap: "wrap",
          }}
        >
          <h2 style={{ margin: 0 }}>{title}</h2>
          {toolbarLeft}
        </Box>

        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            gap: 1,
            minWidth: 0,
            maxWidth: "100%",
            flexWrap: "wrap",
          }}
        >
          {toolbarRight}
          <TextField
            size="small"
            placeholder="Find..."
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setPaginationModel((current) => ({ ...current, page: 0 }));
            }}
            sx={{ width: 260 }}
            InputProps={{
              endAdornment: search ? (
                <InputAdornment position="end">
                  <IconButton
                    aria-label="Svuota filtro generale"
                    size="small"
                    onClick={() => setSearch("")}
                    sx={{ width: 24, height: 24, fontSize: 12 }}
                  >
                    x
                  </IconButton>
                </InputAdornment>
              ) : undefined,
            }}
          />
          {hasActiveFilters && (
            <Button variant="outlined" onClick={clearAllFilters}>
              Rimuovi filtri
            </Button>
          )}
        </Box>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 1 }}>
          {error}
        </Alert>
      )}

      <Box
        sx={{
          position: "relative",
          flex: 1,
          minHeight: 0,
          minWidth: 0,
          width: "100%",
          maxWidth: "100%",
          overflow: "hidden",
        }}
      >
        <DataGrid
          sx={{
            height: "100%",
            width: "100%",
            minHeight: 0,
            minWidth: 0,
            maxWidth: "100%",
            "& .codex-row-locked": {
              bgcolor: "action.disabledBackground",
              color: "text.secondary",
            },
            "& .codex-row-locked:hover": {
              bgcolor: "action.disabledBackground",
            },
            "& .codex-row-compact .MuiDataGrid-cell": {
              alignItems: "flex-start",
              overflow: "hidden",
            },
            "& .codex-row-compact .MuiDataGrid-cell > *": {
              maxHeight: "100%",
              overflow: "hidden",
            },
          }}
          rows={rows}
          columns={dataGridColumns}
          getRowId={getRowId}
          loading={loading}
          rowHeight={rowHeight}
          getRowHeight={getRowHeight}
          getEstimatedRowHeight={() => estimatedRowHeight}
          getRowClassName={getRowClassName}
          isRowSelectable={isRowSelectable}
          columnHeaderHeight={76}
          paginationMode="server"
          rowCount={rowCount}
          paginationModel={paginationModel}
          onPaginationModelChange={(model) => setPaginationModel(model)}
          pageSizeOptions={pageSizeOptions}
          checkboxSelection={checkboxSelection}
          keepNonExistentRowsSelected
          disableRowSelectionOnClick
          rowSelectionModel={rowSelectionModel}
          onRowSelectionModelChange={(newSelection) =>
            setRowSelectionModel(newSelection)
          }
          onRowClick={onRowClick}
          localeText={{ noRowsLabel: emptyMessage }}
          slots={{
            footer: () => (
              <CustomFooter
                selectedCount={selectedIds.size}
                loadedCount={rows.length}
                rowCount={rowCount}
              />
            ),
          }}
        />
      </Box>
    </Box>
  );
}

function CustomFooter({
  selectedCount,
  loadedCount,
  rowCount,
}: {
  selectedCount: number;
  loadedCount: number;
  rowCount: number;
}) {
  return (
    <Box
      sx={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        px: 1,
        py: 0.5,
        borderTop: "1px solid #e0e0e0",
      }}
    >
      <Box sx={{ fontSize: 13, color: "text.secondary" }}>
        {selectedCount > 0
          ? `${selectedCount} righe selezionate`
          : `${loadedCount} righe visualizzate su ${rowCount} totali`}
      </Box>

      <GridPagination />
    </Box>
  );
}
