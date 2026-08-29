ci: clean stage deps style lint

clean:
	rm -rf stage/

stage:
	mkdir -p stage/ stage/gh-pages/

define python_venv
	. .venv/bin/activate && $(1)
endef

rmdeps:
	rm -rf .venv/

deps:
	python3 -m venv .venv
	$(call python_venv,python3 -m pip install -r requirements.txt)

deps-upgrade:
	python3 -m venv .venv
	$(call python_venv,python3 -m pip install --upgrade pip setuptools)
	$(call python_venv,python3 -m pip install -r requirements-dev.txt)
	$(call python_venv,pip-compile --upgrade)

style:
	$(call python_venv,black scripts)

lint: stage
	rm -rf stage/gh-pages/lint/pylint/ stage/lint/ && mkdir -p stage/gh-pages/lint/pylint/ stage/lint/
	find data/ -type f -name "*.json" | while IFS= read -r file; do echo "> $$file"; python3 -m json.tool "$$file"; done
	$(call python_venv,pylint $(shell find scripts -type f -regex ".*\.py" | xargs echo))
	$(call python_venv,pylint $(shell find scripts -type f -regex ".*\.py" | xargs echo) --output-format=pylint_report.CustomJsonReporter > stage/gh-pages/lint/pylint/report.json)
	$(call python_venv,pylint_report stage/gh-pages/lint/pylint/report.json -o stage/gh-pages/lint/pylint/index.html)

build: stage
	test -n "$$OPENROUTER_API_KEY"
	$(call python_venv,python3 scripts/probe.py)

.PHONY: ci clean stage deps deps-upgrade style lint build
