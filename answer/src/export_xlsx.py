"""Portable Excel exporter for questions 1-4.

This exporter uses the project's Python dependency only.  It is intended for
machines that do not have Codex's bundled Node.js and artifact-tool runtime.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import openpyxl


ROOT = Path(__file__).resolve().parents[2]
ANSWER = ROOT / "answer"


def load_rows(question: int) -> list[list[object]]:
    cache = ANSWER / ".cache" / f"q{question}"
    if question == 1:
        data = json.loads((cache / "data.json").read_text(encoding="utf-8"))
        return [[index, *pair] for index, pair in enumerate(data["pairs"], start=1)]
    data = json.loads((cache / "solution.json").read_text(encoding="utf-8"))
    return [list(row) for row in data["rows"]]


def export(question: int) -> Path:
    template = ROOT / "附件" / "附件2" / f"result{question}.xlsx"
    output = ANSWER / "results" / f"result{question}.xlsx"
    rows = load_rows(question)

    book = openpyxl.load_workbook(template)
    sheet = book.active
    expected_columns = sheet.max_column
    if any(len(row) != expected_columns for row in rows):
        raise ValueError(
            f"Question {question} has rows with a column count different from the template"
        )

    # Templates currently contain only the header, but clear any old data rows
    # so rerunning after a different timed solve cannot leave stale records.
    if sheet.max_row > 1:
        for row in sheet.iter_rows(min_row=2, max_row=sheet.max_row,
                                   max_col=expected_columns):
            for cell in row:
                cell.value = None

    for row_index, values in enumerate(rows, start=2):
        for column_index, value in enumerate(values, start=1):
            sheet.cell(row=row_index, column=column_index, value=value)

    output.parent.mkdir(parents=True, exist_ok=True)
    book.save(output)
    book.close()
    print(output)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", type=int, choices=(1, 2, 3, 4))
    args = parser.parse_args()
    export(args.question)
