.PHONY: backend-test frontend-build frontend-lint check

PYTHON ?= /home/omar/miniforge3/envs/interview/bin/python

backend-test:
	$(PYTHON) -m pytest server/tests

frontend-build:
	cd client && npm run build

frontend-lint:
	cd client && npm run lint

check: backend-test frontend-build
