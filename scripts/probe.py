"""Probe each OpenRouter provider configured in promptfoo.yaml and save its response."""

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterator

import yaml
from conflog import Conflog

ROOT_DIR = Path(__file__).resolve().parent.parent
LOGGER = Conflog(conf_files=[str(ROOT_DIR / "config" / "conflog.yaml")]).get_logger(
    "llm-probe"
)


def load_providers(config_path: Path) -> list[str]:
    """Load the provider IDs configured for probing.

    Provider entries may be a plain ID string, or an object with an "id"
    key (used when the provider also carries a "config" block).
    """
    with config_path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    providers = []
    for provider in config.get("providers", []):
        if isinstance(provider, str):
            providers.append(provider)
        elif isinstance(provider, dict) and isinstance(provider.get("id"), str):
            providers.append(provider["id"])
    return providers


def normalize_model_name(provider: str) -> str:
    """Normalise an OpenRouter provider ID into a filesystem-safe model name."""
    model = provider.removeprefix("openrouter:")
    return re.sub(r"[^A-Za-z0-9._-]+", "-", model).strip("-")


def parse_response(raw_response: str) -> dict[str, Any]:
    """Parse a JSON response, retaining non-JSON output for investigation."""
    clean_response = raw_response.strip()
    fenced_match = re.fullmatch(
        r"```(?:json)?\s*(.*?)\s*```", clean_response, flags=re.DOTALL | re.IGNORECASE
    )
    if fenced_match:
        clean_response = fenced_match.group(1).strip()

    try:
        parsed = json.loads(clean_response)
    except json.JSONDecodeError:
        return {"raw_response": clean_response}

    if isinstance(parsed, dict):
        return parsed
    return {"raw_response": clean_response}


def result_rows(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Yield result rows from supported Promptfoo JSON output versions."""
    results = payload.get("results", {})
    if isinstance(results, list):
        yield from (row for row in results if isinstance(row, dict))
        return

    if not isinstance(results, dict):
        return

    for key in ("outputs", "results"):
        rows = results.get(key)
        if isinstance(rows, list):
            yield from (row for row in rows if isinstance(row, dict))
            return


def response_text(row: dict[str, Any]) -> str | None:
    """Extract text returned by a provider from a Promptfoo result row."""
    response = row.get("response")
    if isinstance(response, dict):
        output = response.get("output")
        if isinstance(output, str):
            return output

    output = row.get("output")
    if isinstance(output, str):
        return output
    return None


def response_error(row: dict[str, Any]) -> str | None:
    """Extract an error message from a Promptfoo result row, if any."""
    response = row.get("response")
    if isinstance(response, dict) and isinstance(response.get("error"), str):
        return response["error"]
    if isinstance(row.get("error"), str):
        return row["error"]
    return None


def run_eval(provider: str, config_path: Path, output_path: Path) -> None:
    """Run a Promptfoo eval scoped to a single provider via the promptfoo CLI.

    Promptfoo exits non-zero whenever a test errors (e.g. a provider API
    error), even though it still writes a usable output file, so the
    exit code is deliberately not checked here.
    """
    subprocess.run(
        [
            "promptfoo",
            "eval",
            "--config",
            str(config_path),
            "--filter-providers",
            f"^{re.escape(provider)}$",
            "--var",
            f"model_id={provider.removeprefix('openrouter:')}",
            "--output",
            str(output_path),
        ],
        check=False,
    )


def probe_provider(
    provider: str, config_path: Path, data_dir: Path, stage_dir: Path
) -> bool:
    """Probe a single provider and write its response to the data directory."""
    model_name = normalize_model_name(provider)
    output_path = stage_dir / f"{model_name}.json"
    run_eval(provider, config_path, output_path)

    if not output_path.exists():
        LOGGER.error("promptfoo eval produced no output for %s", provider)
        return False

    with output_path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    for row in result_rows(payload):
        output = response_text(row)
        if output is None:
            error = response_error(row)
            if error:
                LOGGER.error("%s returned an error: %s", provider, error)
            continue
        data_path = data_dir / f"{model_name}.json"
        with data_path.open("w", encoding="utf-8") as file:
            json.dump(parse_response(output), file, indent=2, ensure_ascii=False)
            file.write("\n")
        return True

    return False


def main() -> None:
    """Probe every configured provider and export one JSON file per model."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", type=Path, default=ROOT_DIR / "config" / "promptfoo.yaml"
    )
    parser.add_argument("--data-dir", type=Path, default=ROOT_DIR / "data")
    parser.add_argument("--stage-dir", type=Path, default=ROOT_DIR / "stage")
    parser.add_argument(
        "--delay",
        type=float,
        default=5.0,
        help="Seconds to wait between probing providers, to stay under "
        "OpenRouter's free-tier rate limit (default: 5.0)",
    )
    args = parser.parse_args()

    args.data_dir.mkdir(parents=True, exist_ok=True)
    args.stage_dir.mkdir(parents=True, exist_ok=True)

    providers = load_providers(args.config)
    probed_count = 0
    error_count = 0
    for index, provider in enumerate(providers):
        if index > 0:
            time.sleep(args.delay)
        LOGGER.info("Probing %s", provider)
        if probe_provider(provider, args.config, args.data_dir, args.stage_dir):
            probed_count += 1
        else:
            error_count += 1

    LOGGER.info(
        "Probed %d of %d providers (%d errors).",
        probed_count,
        len(providers),
        error_count,
    )
    if probed_count == 0 and providers:
        sys.exit(1)


if __name__ == "__main__":
    main()
