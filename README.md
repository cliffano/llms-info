# llm-probe

Run [`prompt.txt`](prompt.txt) against the free models configured in
[`config/promptfoo.yaml`](config/promptfoo.yaml) through OpenRouter.
Successful JSON responses are exported to one `data/openrouter.*.json` file per
model for use by the existing pandas report generator.

## Setup

Create an OpenRouter API key, export it, and install the dependencies:

```sh
export OPENROUTER_API_KEY="..."
make deps
```

## Run

```sh
make build
```

Each configured provider is probed individually via `promptfoo eval`.
Promptfoo's raw result for each provider, including errors and token
metadata, is saved to `stage/<model>.json`; the successful response body is
exported to `data/<model>.json`.

OpenRouter changes its free catalog over time. Update the explicit `providers`
list in `config/promptfoo.yaml` when you want to change the probe set.
