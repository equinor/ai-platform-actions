"""
Outer Loop Action — Main Entry Point

Routes verb/subject pairs to the appropriate command module.
"""

import typer
from . import evaluate
from . import compare
from . import report
from . import check

app = typer.Typer()

app.add_typer(evaluate.app, name="evaluate")
app.add_typer(compare.app, name="compare")
app.add_typer(report.app, name="report")
app.add_typer(check.app, name="check")

if __name__ == "__main__":
    app()
