"""Cloud Run gateway entrypoint for DB-backed sessions and media uploads."""

from __future__ import annotations

import os

from tailmate.adapters.db_gateway.gateway_app import create_app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
