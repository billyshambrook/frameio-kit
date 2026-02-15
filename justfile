# Build the project
build:
    uv sync

# Run tests
test: build
    uv run --frozen pytest -xvs tests


static-checks: build
    uv run prek run --all-files

docs:
    uv run zensical serve