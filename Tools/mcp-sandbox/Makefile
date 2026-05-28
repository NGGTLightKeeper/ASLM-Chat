IMAGE       ?= nggtlightkeeper/aslm-chat-sandbox:latest
CONTAINER   ?= aslm-chat-sandbox
PYTEST_ARGS ?= -q

# Run all host-side tests (no Docker required).
.PHONY: test-host
test-host:
	python -m pytest $(PYTEST_ARGS)

# Run tests inside the container image (requires a built image).
# Mounts the test suite read-only so the container runs the latest tests
# against the baked-in supervisor code.
.PHONY: test-container
test-container:
	docker run --rm \
	  -e SANDBOX_IN_CONTAINER=1 \
	  -e SANDBOX_HOST_WORKSPACE=/workspace \
	  -v "$(CURDIR)/tests:/opt/sandbox-tests:ro" \
	  --entrypoint "" \
	  $(IMAGE) \
	  /opt/sandbox-venv/bin/python -m pytest /opt/sandbox-tests $(PYTEST_ARGS)

# Build the Docker image locally.
.PHONY: build
build:
	docker build -t $(IMAGE) .
