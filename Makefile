# macOS / Linux shortcuts. On Windows use run.bat (or run.ps1) with the same command names.
.PHONY: install doctor run test test-e2e seed unseed smoke warm eval bench tunnel

install:
	pip install -r requirements-dev.txt

doctor:
	python -m scripts.doctor

run:
	uvicorn app.main:app --host 0.0.0.0 --port 8000

test:
	python -m pytest -q --ignore=tests/e2e

test-e2e:
	python -m pytest -q tests/e2e

seed:
	python -m scripts.seed_demo

unseed:
	python -m scripts.seed_demo --clear

smoke:
	python -m scripts.smoke

warm:
	python -m scripts.warm_tts

eval:
	python -m bench.text_eval

bench:
	python -m bench.make_noisy && python -m bench.run_bench

tunnel:
	cloudflared tunnel --url http://localhost:8000
