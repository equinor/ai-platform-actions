FROM astral/uv:python3.12-bookworm-slim
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1
COPY pyproject.toml share_component.py ./
RUN uv sync
ENV PATH="/app/.venv/bin:$PATH"

ENTRYPOINT ["uv", "run", "python", "/app/share_component.py"]
