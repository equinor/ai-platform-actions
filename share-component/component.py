from azure.identity import DefaultAzureCredential
from azure.ai.ml import MLClient, load_component
from pathlib import Path
import time
import os

# SOURCE WORKSPACE
# -------------------------------
SUB_ID   = "019958ea-fe2c-4e14-bbd9-0d2db8ed7cfc"
WS_RG    = "unified-rg-dev"
WS_NAME  = "unified-amlws-dev"

# TARGET REGISTRY
# -------------------------------
REG_RG   = "unified-rg-shrd"
REG_NAME = "unified-aml-reg-shrd"

credential = DefaultAzureCredential()
# --- Connect to workspace ---
ml = MLClient(
    credential=DefaultAzureCredential(),
    subscription_id=SUB_ID,
    resource_group_name=WS_RG,
    workspace_name=WS_NAME
)

# --- Get the component you want to download ---
comp = ml.components.get(name="train_test_split", version="2025-11-19-15-02-26-5694839")

# --- Download EVERYTHING (code + yaml + metadata) ---
download_path = Path("./downloaded_component")
ml.components.download(
    name=comp.name,
    version=comp.version,
    download_path=download_path
)

print("Downloaded to:", download_path.resolve())

credential = DefaultAzureCredential()

# ---- Registry client ----
ml_client_reg = MLClient(
    credential=credential,
    subscription_id=SUB_ID,
    resource_group_name=REG_RG,
    registry_name=REG_NAME
)

# Load component from Downloaded folder
downloaded_path = "./downloaded_component/component_spec.yaml"
downloaded_path = os.path.abspath(downloaded_path)

print("Loading component from:", downloaded_path)
comp = load_component(downloaded_path)

comp.version = str(int(time.time()))

print("Uploading to registry:", REG_NAME)
ml_client_reg.components.create_or_update(comp)

print(f"Successfully uploaded as version {comp.version}")

