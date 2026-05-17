"""Cloud Run entrypoint for the Tailmate Vertex AI test UI."""

from tailmate.entrypoints.vertex_test_ui import create_app

app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
