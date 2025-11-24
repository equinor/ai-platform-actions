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

# Load data asset
data = ml.data.get(name="dataset", version="c02abe86")


ml_client_reg = MLClient(
    credential=credential,
    subscription_id=SUB_ID,
    resource_group_name=REG_RG,
    registry_name=REG_NAME
)
data.name = "sampledata"
data.version = "16"
ml_client_reg.data.create_or_update(data)
