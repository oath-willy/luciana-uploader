import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import ServerDataGrid, { ServerGridFetchParams, ServerGridResult } from "./ServerDataGrid";

jest.mock("@mui/x-data-grid", () => ({
  useGridApiRef: () => ({ current: null }),
  DataGrid: (props: any) => (
    <div>
      <div data-testid="rows">{JSON.stringify(props.rows)}</div>
      <button onClick={() => props.onPaginationModelChange({ page: props.paginationModel.page + 1, pageSize: 25 })}>Next page</button>
      <button onClick={() => props.onRowSelectionModelChange({ type: "include", ids: new Set([props.rows[0].id]) })}>Select first</button>
    </div>
  ),
}));

function deferred() {
  let resolve!: (result: ServerGridResult) => void;
  const promise = new Promise<ServerGridResult>((done) => { resolve = done; });
  return { promise, resolve };
}

test("aborts obsolete requests and ignores their late responses", async () => {
  const oldRequest = deferred();
  const newRequest = deferred();
  const fetchRows = jest.fn((_: ServerGridFetchParams) => oldRequest.promise);
  const columns = [{ field: "id" }];
  const view = render(<ServerDataGrid title="Test" columns={columns} fetchRows={fetchRows} refreshToken={0} />);
  await waitFor(() => expect(fetchRows).toHaveBeenCalledTimes(1));
  const oldSignal = fetchRows.mock.calls[0][0].signal;
  fetchRows.mockImplementation(() => newRequest.promise);
  view.rerender(<ServerDataGrid title="Test" columns={columns} fetchRows={fetchRows} refreshToken={1} />);
  expect(oldSignal?.aborted).toBe(true);
  await act(async () => newRequest.resolve({ rows: [{ id: 2, description: "latest" }], total: 1 }));
  await act(async () => oldRequest.resolve({ rows: [{ id: 1, description: "obsolete" }], total: 1 }));
  expect(screen.getByTestId("rows").textContent).toContain("latest");
  expect(screen.getByTestId("rows").textContent).not.toContain("obsolete");
  const newSignal = fetchRows.mock.calls[1][0].signal;
  view.unmount();
  expect(newSignal?.aborted).toBe(true);
});

test("preserves selected row data when evicting previously visited pages", async () => {
  const fetchRows = jest.fn(async (params: ServerGridFetchParams) => ({ rows: [{ id: params.page + 1 }], total: 100 }));
  const onSelectionChange = jest.fn();
  render(<ServerDataGrid title="Test" columns={[{ field: "id" }]} fetchRows={fetchRows}
    onSelectionChange={onSelectionChange} defaultPageSize={25} />);
  await waitFor(() => expect(screen.getByTestId("rows").textContent).toContain('"id":1'));
  fireEvent.click(screen.getByText("Select first"));
  await waitFor(() => expect(onSelectionChange).toHaveBeenLastCalledWith(new Set([1]), [{ id: 1 }]));
  fireEvent.click(screen.getByText("Next page"));
  await waitFor(() => expect(screen.getByTestId("rows").textContent).toContain('"id":2'));
  expect(onSelectionChange).toHaveBeenLastCalledWith(new Set([1]), [{ id: 1 }]);
  fireEvent.click(screen.getByText("Select first"));
  await waitFor(() => expect(onSelectionChange).toHaveBeenLastCalledWith(new Set([2]), [{ id: 2 }]));
  fireEvent.click(screen.getByText("Next page"));
  await waitFor(() => expect(screen.getByTestId("rows").textContent).toContain('"id":3'));
  expect(onSelectionChange).toHaveBeenLastCalledWith(new Set([2]), [{ id: 2 }]);
});
