import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import CommitCell from "./CommitCell";

test("typing alone does not save; blur and Escape discard uncommitted changes", () => {
  const save = jest.fn(async () => {});
  render(<CommitCell value="Original" label="Cell" onCommit={save} />);
  const cell = screen.getByRole("textbox", { name: "Cell" });
  fireEvent.change(cell, { target: { value: "Draft" } }); fireEvent.blur(cell);
  expect(cell).toHaveValue("Original"); expect(save).not.toHaveBeenCalled();
  fireEvent.change(cell, { target: { value: "Draft" } }); fireEvent.keyDown(cell, { key: "Escape" });
  expect(cell).toHaveValue("Original"); expect(save).not.toHaveBeenCalled();
});

test("invalid saves keep the draft and mark the cell invalid", async () => {
  const save = jest.fn(async () => { throw new Error("Valore non valido"); });
  render(<CommitCell value="" label="Cell" onCommit={save} />);
  const cell = screen.getByRole("textbox", { name: "Cell" });
  fireEvent.change(cell, { target: { value: "Bad" } }); fireEvent.keyDown(cell, { key: "Enter" });
  await waitFor(() => expect(cell).toHaveAttribute("aria-invalid", "true"));
  expect(cell).toHaveValue("Bad");
});
