"""
Command-line interface for the healthcare CRM agent.

Provides utilities for database management, testing, and operations.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from sqlalchemy import text

from healthcare_agent.config import settings
from healthcare_agent.models.database import Base
from sqlalchemy import create_engine, text

# Create sync engine for CLI
sync_engine = create_engine("sqlite:///hcrm.db")

app = typer.Typer()


@app.command()
def init_db():
    """Initialize the database with tables."""
    with sync_engine.begin() as conn:
        # Create tables
        Base.metadata.create_all(conn)
        typer.echo("Database tables created successfully.")


@app.command()
def reset_db():
    """Reset the database (drop and recreate all tables)."""
    with sync_engine.begin() as conn:
        # Drop all tables
        Base.metadata.drop_all(conn)
        # Create tables
        Base.metadata.create_all(conn)
        typer.echo("Database reset successfully.")


@app.command()
def test_connection():
    """Test database connection."""
    try:
        with sync_engine.begin() as conn:
            result = conn.execute(text("SELECT 1"))
            typer.echo("Database connection successful.")
    except Exception as e:
        typer.echo(f"Database connection failed: {e}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()