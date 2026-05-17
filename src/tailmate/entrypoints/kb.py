"""Knowledge base developer entrypoints."""

from __future__ import annotations

import argparse
import json
import sys

from tailmate.adapters.knowledge_base.management import (
    build_vertex_embedding_client,
    reindex_knowledge_chunks,
)
from tailmate.entrypoints.local_env import build_local_container


def add_kb_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the `kb` command group."""

    parser = subparsers.add_parser(
        "kb",
        help="Operate on the reviewed knowledge base from the local developer CLI.",
    )
    kb_subparsers = parser.add_subparsers(dest="kb_command", required=True)

    reindex_parser = kb_subparsers.add_parser(
        "reindex",
        help="Rebuild embeddings for all reviewed knowledge chunks.",
    )
    reindex_parser.set_defaults(func=run_kb_reindex)


def run_kb_reindex(args: argparse.Namespace) -> int:
    """Rebuild embeddings for the direct knowledge base."""

    del args
    container = build_local_container()
    if container.config.uses_db_gateway:
        print("Knowledge reindexing requires direct database mode.", file=sys.stderr)
        return 1

    embedding_client = build_vertex_embedding_client(
        model_name=container.config.embedding_model,
        project_id=container.config.project_id,
        location=container.config.location,
        api_key=container._get_actual_gemini_api_key(),
        credentials=container._get_vertex_ai_credentials(),
    )
    result = reindex_knowledge_chunks(
        container.build_engine_factory(),
        embedding_client=embedding_client,
    )
    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0
