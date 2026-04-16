FROM python:3.13

WORKDIR /app

# Install uv
ADD --chmod=755 https://astral.sh/uv/install.sh /install.sh
RUN /install.sh && rm /install.sh

ENV PATH="/root/.local/bin/:$PATH"

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen

COPY . .

ENTRYPOINT [ "bash", "_CI/entrypoint.sh"]
