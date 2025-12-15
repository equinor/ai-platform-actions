FROM astral/uv:python3.13-bookworm-slim
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1

# Copy project files
COPY pyproject.toml ./
COPY src/ ./src/

# Install dependencies and build the package
RUN uv sync

# Add the virtual environment to PATH
ENV PATH="/app/.venv/bin:$PATH"

# Entrypoint that isolates from host context
# The --isolated flag prevents uv from looking for pyproject.toml/uv.lock in the current working directory
# The -m flag runs the module as a script
ENTRYPOINT ["python", "-m", "aip.inner.main"]