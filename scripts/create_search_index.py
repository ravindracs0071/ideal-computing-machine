#!/usr/bin/env python3
"""Create or update the Azure AI Search index from the schema in infra/azure_search/index.json.

Usage:
    python scripts/create_search_index.py

Environment variables required:
    AZURE_SEARCH_ENDPOINT
    AZURE_SEARCH_API_KEY
    AZURE_SEARCH_INDEX      (optional – overrides the name in index.json)
    EMBEDDING_DIMENSIONS    (optional – overrides contentVector dimensions in index.json)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Allow running from repo root without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def load_schema() -> dict:
    schema_path = Path(__file__).resolve().parents[1] / "infra" / "azure_search" / "index.json"
    with schema_path.open() as f:
        return json.load(f)


def apply_overrides(schema: dict) -> dict:
    """Apply environment-variable overrides to the schema."""
    # Index name override
    index_name = os.environ.get("AZURE_SEARCH_INDEX")
    if index_name:
        schema["name"] = index_name

    # Embedding dimensions override
    dims_str = os.environ.get("EMBEDDING_DIMENSIONS")
    if dims_str:
        dims = int(dims_str)
        for field in schema.get("fields", []):
            if field.get("name") == "contentVector":
                field["dimensions"] = dims
                break

    return schema


def create_or_update_index(schema: dict) -> None:
    from azure.core.credentials import AzureKeyCredential
    from azure.search.documents.indexes import SearchIndexClient
    from azure.search.documents.indexes.models import SearchIndex

    endpoint = os.environ["AZURE_SEARCH_ENDPOINT"]
    api_key = os.environ["AZURE_SEARCH_API_KEY"]

    client = SearchIndexClient(
        endpoint=endpoint,
        credential=AzureKeyCredential(api_key),
    )

    index = SearchIndex.deserialize(schema)
    result = client.create_or_update_index(index)
    print(f"✓ Index '{result.name}' created/updated successfully.")


def main() -> None:
    schema = load_schema()
    schema = apply_overrides(schema)
    print(f"Creating/updating index: {schema['name']}")
    create_or_update_index(schema)


if __name__ == "__main__":
    main()
