SHELL := /bin/bash

.PHONY: help setup up down logs test lint docs-check host-check agent-create agent-start agent-stop agent-status agent-auth agent-export agent-import user-create

help:
	@./scripts/workspace.sh help

setup:
	@./scripts/workspace.sh setup

up:
	@./scripts/workspace.sh up

down:
	docker compose --env-file .env -f infra/orchestration/docker-compose/docker-compose.yml down

logs:
	docker compose --env-file .env -f infra/orchestration/docker-compose/docker-compose.yml logs -f

test:
	@./scripts/workspace.sh test

lint:
	@./scripts/workspace.sh lint

docs-check:
	@./scripts/workspace.sh docs-check

host-check:
	@./scripts/workspace.sh host-check

agent-create agent-start agent-stop agent-status agent-auth agent-export agent-import user-create:
	@./scripts/workspace.sh $@ "$(AGENT)" "$(ARGS)"
