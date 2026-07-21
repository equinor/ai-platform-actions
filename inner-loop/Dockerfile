FROM astral/uv:python3.13-bookworm-slim
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1

# Copy project files
COPY pyproject.toml uv.lock ./
COPY src/ ./src/

# Install dependencies and build the package
RUN uv sync --locked

# Add the virtual environment to PATH
ENV PATH="/app/.venv/bin:$PATH"

ENTRYPOINT ["python", "-m", "aip.inner.action_entrypoint"]