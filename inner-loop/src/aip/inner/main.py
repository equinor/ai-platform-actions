"""
Inner Loop Action - Main Entry Point

Routes to deploy.py or share.py based on the verb.
"""

import typer
from typing import Optional
from . import deploy
from . import share

app = typer.Typer()

# Add deploy and share sub-apps
app.add_typer(deploy.app, name="deploy")
app.add_typer(share.app, name="share")

if __name__ == "__main__":
    app()
