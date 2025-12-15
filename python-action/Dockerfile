# Use a Python base image with uv
#FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
#FROM astral/uv:python3.12-alpine
FROM astral/uv:python3.12-bookworm-slim
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1
COPY pyproject.toml subapp.py ./
RUN uv sync
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000

ENTRYPOINT ["uv", "run", "python", "/app/subapp.py"]
CMD ["--help"]