FROM astral/uv:python3.12-bookworm-slim
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1
COPY pyproject.toml __init__.py util.py main.py deploy.py share.py ./
RUN uv sync
ENV PATH="/app/.venv/bin:$PATH"

ENTRYPOINT ["uv", "run", "python", "/app/main.py"]
