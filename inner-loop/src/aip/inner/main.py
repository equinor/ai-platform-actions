"""
Inner Loop Action - Main Entry Point

Routes to deploy.py or share.py based on the verb.
"""

import typer
from typing import Optional
from . import deploy
from . import share
from . import waitfor
from . import delete
from . import rollback
from . import invoke
from . import promote

app = typer.Typer()

# Add deploy and share sub-apps
app.add_typer(deploy.app, name="deploy")
app.add_typer(share.app, name="share")
app.add_typer(waitfor.app, name="waitfor")
app.add_typer(delete.app, name="delete")
app.add_typer(rollback.app, name="rollback")
app.add_typer(invoke.app, name="invoke")
app.add_typer(promote.app, name="promote")

if __name__ == "__main__":
    app()
