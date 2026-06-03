from __future__ import annotations

import csv
import gzip
import sys
from itertools import chain
from pathlib import Path
from typing import Any


def open_file(path: str | Path, mode: str):
    file_path = str(path)
    if file_path.endswith(".gz"):
        return gzip.open(file_path, mode, encoding="utf-8", newline="")
    return open(file_path, mode, encoding="utf-8", newline="")


def detect_delimiter(header_line: str) -> str:
    candidates = ["\t", ",", ";"]
    best_sep = "\t"
    best_count = -1
    for sep in candidates:
        count = header_line.count(sep)
        if count > best_count:
            best_sep = sep
            best_count = count
    return best_sep if best_count > 0 else "\t"


def normalize_cell(value: Any) -> str:
    return str(value or "").strip().strip('"').strip("'").lstrip("\ufeff")


def find_gene_id_col(header: list[str]) -> int:
    for index, value in enumerate(header):
        normalized = normalize_cell(value).lower().replace(" ", "").replace("-", "").replace(".", "")
        if normalized in {"gene_id", "geneid"}:
            return index
    return -1


def fix_row_width(row: list[str], width: int) -> list[str]:
    if len(row) < width:
        return row + [""] * (width - len(row))
    if len(row) > width:
        return row[:width]
    return row


def _read_annotation(annotation_file: str | Path) -> dict[str, Any]:
    annotation_dict: dict[str, list[str]] = {}
    duplicate_count = 0
    with open_file(annotation_file, "rt") as handle:
        first_line = handle.readline()
        if not first_line:
            return {
                "status": "annotation_empty",
                "warning": "Annotation file is empty.",
                "header": [],
                "rows_by_gene_id": {},
                "column_count": 0,
                "duplicate_count": 0,
            }

        delimiter = detect_delimiter(first_line)
        reader = csv.reader(chain([first_line], handle), delimiter=delimiter)
        header = next(reader)
        gene_col = find_gene_id_col(header)
        if gene_col < 0:
            return {
                "status": "annotation_missing_gene_id",
                "warning": "gene_id column was not found in annotation file.",
                "header": header,
                "rows_by_gene_id": {},
                "column_count": len(header),
                "duplicate_count": 0,
            }

        column_count = len(header)
        for row in reader:
            if not row:
                continue
            fixed = fix_row_width(row, column_count)
            gene_id = normalize_cell(fixed[gene_col])
            if not gene_id:
                continue
            if gene_id not in annotation_dict:
                annotation_dict[gene_id] = fixed
            else:
                duplicate_count += 1

    return {
        "status": "completed",
        "warning": "",
        "header": header,
        "rows_by_gene_id": annotation_dict,
        "column_count": len(header),
        "duplicate_count": duplicate_count,
    }


def merge_gene_annotation_files(
    transcriptome_file: str | Path,
    annotation_file: str | Path,
    output_file: str | Path,
) -> dict[str, Any]:
    transcriptome_path = Path(transcriptome_file)
    annotation_path = Path(annotation_file)
    output_path = Path(output_file)
    result = {
        "status": "completed",
        "warning": "",
        "total_count": 0,
        "matched_count": 0,
        "unmatched_count": 0,
        "duplicate_count": 0,
        "output_file": str(output_path),
    }

    if not annotation_path.is_file():
        result["status"] = "annotation_missing"
        result["warning"] = f"Annotation file not found: {annotation_path}"
        result["output_file"] = ""
        return result
    if not transcriptome_path.is_file():
        result["status"] = "transcriptome_missing"
        result["warning"] = f"Transcriptome file not found: {transcriptome_path}"
        result["output_file"] = ""
        return result

    annotation_info = _read_annotation(annotation_path)
    result["status"] = str(annotation_info.get("status") or "completed")
    result["warning"] = str(annotation_info.get("warning") or "")
    result["duplicate_count"] = int(annotation_info.get("duplicate_count") or 0)
    if result["status"] != "completed":
        result["output_file"] = ""
        return result

    annotation_header = list(annotation_info["header"])
    annotation_dict = dict(annotation_info["rows_by_gene_id"])
    annotation_col_count = int(annotation_info["column_count"])

    with open_file(transcriptome_path, "rt") as fin:
        first_line = fin.readline()
        if not first_line:
            result["status"] = "transcriptome_empty"
            result["warning"] = "Transcriptome file is empty."
            result["output_file"] = ""
            return result

        delimiter = detect_delimiter(first_line)
        reader = csv.reader(chain([first_line], fin), delimiter=delimiter)
        transcriptome_header = next(reader)
        gene_col = find_gene_id_col(transcriptome_header)
        if gene_col < 0:
            result["status"] = "transcriptome_missing_gene_id"
            result["warning"] = "gene_id column was not found in transcriptome file."
            result["output_file"] = ""
            return result

        transcriptome_col_count = len(transcriptome_header)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open_file(output_path, "wt") as fout:
            writer = csv.writer(fout, delimiter=delimiter, lineterminator="\n")
            writer.writerow(transcriptome_header + annotation_header)
            for row in reader:
                if not row:
                    continue
                result["total_count"] += 1
                fixed = fix_row_width(row, transcriptome_col_count)
                gene_id = normalize_cell(fixed[gene_col])
                if gene_id in annotation_dict:
                    writer.writerow(fixed + annotation_dict[gene_id])
                    result["matched_count"] += 1
                else:
                    writer.writerow(fixed + [""] * annotation_col_count)
                    result["unmatched_count"] += 1

    return result


def main(argv: list[str] | None = None) -> int:
    args = list(argv or sys.argv[1:])
    if len(args) != 3:
        print(
            f"Usage: python {Path(__file__).name} transcriptome_file annotation_file output_file",
            file=sys.stderr,
        )
        return 1

    result = merge_gene_annotation_files(args[0], args[1], args[2])
    if result["status"] != "completed":
        print(f"Error: {result['warning']}", file=sys.stderr)
        return 1

    print(f"Total transcriptome rows: {result['total_count']}", file=sys.stderr)
    print(f"Matched rows: {result['matched_count']}", file=sys.stderr)
    print(f"Unmatched rows: {result['unmatched_count']}", file=sys.stderr)
    print(f"Duplicated annotation gene_id ignored: {result['duplicate_count']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
