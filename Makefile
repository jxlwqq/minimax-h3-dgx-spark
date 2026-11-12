.DEFAULT_GOAL := help
SHELL := /usr/bin/env bash

DATA_ROOT ?=

.PHONY: help init preflight prepare-source build rebuild gpu-check download download-r2v verify-models check-model-source smoke test up stop restart logs status diagnostics clean-container

help:
	@echo "MiniMax H3 / DGX Spark commands"
	@echo ""
	@echo "  make init DATA_ROOT=/mnt/<4tb>/minimax-h3"
	@echo "  make preflight"
	@echo "  make build"
	@echo "  make gpu-check"
	@echo "  make download"
	@echo "  make up"
	@echo "  make logs"
	@echo "  make status"
	@echo "  make download-r2v"
	@echo "  make diagnostics"
	@echo "  make check-model-source  # ModelScope metadata, no weights downloaded"
	@echo "  make smoke               # generate and validate a short video with audio"
	@echo "  make test                # local regression tests, no GPU required"

init:
	@if [[ -z "$(DATA_ROOT)" ]]; then \
		echo "ERROR: use make init DATA_ROOT=/mnt/<4tb>/minimax-h3"; exit 2; \
	fi
	@./scripts/init_storage.sh "$(DATA_ROOT)"

preflight:
	@./scripts/preflight.sh

prepare-source:
	@./scripts/prepare_comfyui_src.sh

build: prepare-source
	@docker compose build

rebuild: prepare-source
	@docker compose build --no-cache

gpu-check:
	@docker compose run --rm --no-deps --entrypoint /opt/nvidia/nvidia_entrypoint.sh \
	  comfyui python /usr/local/bin/h3-validate-runtime

download:
	@./scripts/download_fl2va.sh

download-r2v:
	@./scripts/download_ref2va.sh

verify-models:
	@./scripts/verify_models.sh

check-model-source:
	@./scripts/check_model_source.sh

smoke:
	@./scripts/smoke.sh

test:
	@python3 -m unittest discover -s tests -v

up:
	@docker compose up -d
	@echo "ComfyUI: http://127.0.0.1:$${COMFYUI_PORT:-8188}"

stop:
	@docker compose down

restart:
	@docker compose down
	@docker compose up -d

logs:
	@docker compose logs -f --tail=200 comfyui

status:
	@./scripts/status.sh

diagnostics:
	@./scripts/collect_diagnostics.sh

clean-container:
	@docker compose down --remove-orphans
	@docker image rm "local/minimax-h3-comfyui:$${COMFYUI_REF:-v0.45.0}" 2>/dev/null || true
