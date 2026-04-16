#!/bin/bash
set -e

uv run alembic upgrade head

uv run python app/bot.py
