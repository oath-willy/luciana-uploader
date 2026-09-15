import { fireEvent, render, screen } from "@testing-library/react";
import ItemsCode from "./ItemsCode";

jest.mock("./itemsCode/DatasetTable", () => {
  const React = require("react");
  return { __esModule: true, default: (props: any) => {
    const [value, setValue] = React.useState("");
    return <div>{props.title}{props.dataset === "new-items" && <>
      <input aria-label="Upper selection" value={value} onChange={(event) => setValue(event.target.value)} />
      <button onClick={() => props.onReferenceVisibleChange(!props.referenceVisible)}>Reference PDB toggle</button>
    </>}</div>;
  }};
});

test("Reference is initially unmounted; toggling preserves upper table state", () => {
  render(<ItemsCode />);
  expect(screen.queryByText("Reference PDB", { exact: true })).not.toBeInTheDocument();
  expect(screen.queryByRole("separator")).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Upper selection"), { target: { value: "IVOCLAR" } });
  fireEvent.click(screen.getByText("Reference PDB toggle"));
  expect(screen.getByText("Reference PDB", { exact: true })).toBeInTheDocument();
  expect(screen.getByRole("separator")).toBeInTheDocument();
  fireEvent.click(screen.getByText("Reference PDB toggle"));
  expect(screen.queryByText("Reference PDB", { exact: true })).not.toBeInTheDocument();
  expect(screen.getByLabelText("Upper selection")).toHaveValue("IVOCLAR");
});
