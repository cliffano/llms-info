"""Collate the per-model JSON files under data/ into an HTML report under stage/."""

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd
from conflog import Conflog
from pandasreporter import PandasReporter

ROOT_DIR = Path(__file__).resolve().parent.parent
LOGGER = Conflog(conf_files=[str(ROOT_DIR / "config" / "conflog.yaml")]).get_logger(
    "llm-probe"
)


def flatten_dict(
    nested: dict[str, Any], parent_key: str = "", sep: str = "_"
) -> dict[str, Any]:
    """Flatten a nested dictionary, joining keys with sep."""
    items = []
    for key, value in nested.items():
        new_key = f"{parent_key}{sep}{key}" if parent_key else key
        if isinstance(value, dict):
            items.extend(flatten_dict(value, new_key, sep=sep).items())
        elif isinstance(value, (list, tuple)):
            items.append((new_key, json.dumps(value)))
        else:
            items.append((new_key, value))
    return dict(items)


def load_model_data(data_dir: Path) -> dict[str, dict[str, Any]]:
    """Load and flatten every model JSON file, keyed by model name."""
    collated_data = {}
    for json_file in sorted(data_dir.glob("*.json")):
        try:
            with json_file.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError) as error:
            LOGGER.error("Error loading %s: %s", json_file.name, error)
            continue
        collated_data[json_file.stem] = flatten_dict(data)
        LOGGER.info("Loaded: %s", json_file.name)
    return collated_data


def build_report_dataframe(collated_data: dict[str, dict[str, Any]]) -> pd.DataFrame:
    """Build a fields x models DataFrame from collated model data."""
    df = pd.DataFrame(collated_data)
    return df.reset_index().rename(columns={"index": "field"})


def write_report(df_report: pd.DataFrame, output_path: Path) -> bool:
    """Render the report DataFrame to an HTML file, returning success."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pandas_reporter = PandasReporter()
    pandas_reporter.report(
        df_report,
        "html",
        {
            "title": "LLM Probe Report",
            "generator": "llm-probe",
            "max_col_size": 80,
            "out_file": str(output_path),
        },
    )
    return output_path.exists() and output_path.stat().st_size > 0


def main() -> None:
    """Collate every model JSON file under data/ into an HTML report."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=ROOT_DIR / "data")
    parser.add_argument("--stage-dir", type=Path, default=ROOT_DIR / "stage")
    args = parser.parse_args()

    LOGGER.info("Reading data from: %s", args.data_dir)
    collated_data = load_model_data(args.data_dir)
    if not collated_data:
        LOGGER.error("No JSON data loaded from: %s", args.data_dir)
        return

    df_report = build_report_dataframe(collated_data)
    LOGGER.info(
        "Created DataFrame with %d rows and %d columns",
        len(df_report),
        len(df_report.columns),
    )

    output_path = args.stage_dir / "llm-probe-report.html"
    if not write_report(df_report, output_path):
        LOGGER.error("pandasreporter did not generate a non-empty report")
        return

    LOGGER.info("Report generated: %s", output_path)


if __name__ == "__main__":
    main()
