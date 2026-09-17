import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import McCode from "./McCode";

jest.mock("./common/ServerDataGrid", () => ({
  __esModule: true,
  default: (props: any) => {
    const row = { id: "DEALER::A1", item_code: "A1", company_item_code: "DEALER|A1", description: "Ceramic brush",
      bs25_status: "completed", bs25_selection_status: "completed", bs25_selected_source: "bs25" };
    return <div>{props.toolbarLeft}<button onClick={() => {
      if (props.isRowSelectable({ row })) props.onSelectionChange(new Set([row.id]), [row]);
    }}>Select saved BS25 item</button>{props.columns.filter((c: any) => props.columnVisibilityModel?.[c.field] !== false)
      .map((c: any) => <span key={c.field}>{c.headerName}</span>)}</div>;
  },
}));

test("PAC-AI has its own group and can classify a previously saved BS25 item", async () => {
  const requests: Array<{ url: string; body: any }> = [];
  const originalFetch = global.fetch;
  global.fetch = jest.fn(async (url: any, init: any) => {
    requests.push({ url: String(url), body: init?.body ? JSON.parse(init.body) : null });
    const value = String(url).endsWith("/config") ? {
      default_environment: "dev", environments: [{ value: "dev", label: "Dev", available: true }],
      dataset_name: "New Items", pac_ai: { available: true, max_batch_size: 100 },
    } : String(url).includes("/companies?") ? [{ value: "DEALER", label: "DEALER", full_view_available: true }]
      : String(url).endsWith("/pac-ai") ? { accepted_item_codes: ["A1"], locked_item_codes: [] }
      : { active: false, updated: 0 };
    return { ok: true, json: async () => value } as Response;
  }) as any;
  const { unmount } = render(<McCode />);
  try {
    await waitFor(() => expect(screen.getByRole("combobox", { name: "Company" })).not.toBeDisabled());
    fireEvent.change(screen.getByRole("combobox", { name: "Company" }), { target: { value: "DEA" } });
    fireEvent.click(await screen.findByRole("option", { name: "DEALER" }));
    expect(screen.getByRole("group", { name: "Azioni PAC-AI" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Fuzzy Lookup" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "AI Lookup" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Select saved BS25 item"));
    fireEvent.click(screen.getByRole("button", { name: "PAC-AI (1)" }));
    await waitFor(() => expect(requests.some((r) => r.url.endsWith("/pac-ai") && r.body.item_codes[0] === "A1")).toBe(true));
    expect(screen.getByText("Master Code PAC-AI")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("switch", { name: "Mostra colonne BS25 e BS25AI" }));
    expect(screen.queryByText("Proposta BS25 1")).not.toBeInTheDocument();
    expect(screen.queryByText("BS25AI", { selector: "span" })).not.toBeInTheDocument();
    expect(screen.getByText("Master Code PAC-AI")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("switch", { name: "Mostra colonne PAC-AI" }));
    expect(screen.queryByText("Master Code PAC-AI")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("switch", { name: "Mostra colonne BS25 e BS25AI" }));
    expect(screen.getByText("Proposta BS25 1")).toBeInTheDocument();
    expect(screen.queryByText("Master Code PAC-AI")).not.toBeInTheDocument();
  } finally {
    unmount();
    global.fetch = originalFetch;
  }
});
