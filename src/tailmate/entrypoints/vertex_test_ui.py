"""Cloud Run test UI for invoking a deployed Vertex AI Agent Engine."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from collections.abc import Iterator
import mimetypes
import os
from typing import Any
from uuid import uuid4

from flask import Flask, Response, current_app, jsonify, render_template_string, request, stream_with_context
from google.cloud import storage
import requests
from werkzeug.exceptions import RequestEntityTooLarge
import vertexai

from tailmate.contracts.constants import STRIP_METADATA_REQUEST_METADATA_KEY
from tailmate.contracts.types import (
    normalize_query_message,
    normalize_strip_metadata_request,
    resolve_media_upload_limit,
)
from tailmate.contracts.errors import InternalError


DEFAULT_MAX_UPLOAD_BYTES = 50 * 1024 * 1024
DEFAULT_TEXT_PROMPT = "My dog is Peanut."
DEFAULT_UPLOAD_PROMPT = "Please sanitize and store this upload."
PAGE_TEMPLATE = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{{ page.title }}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link
      href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Space+Grotesk:wght@400;500;700&display=swap"
      rel="stylesheet"
    >
    <style>
      :root {
        --bg: #0a0d14;
        --bg-2: #111826;
        --panel: rgba(15, 21, 34, 0.82);
        --panel-strong: rgba(14, 20, 31, 0.94);
        --line: rgba(134, 170, 255, 0.18);
        --line-strong: rgba(134, 170, 255, 0.38);
        --text: #eef4ff;
        --muted: #9db0cc;
        --accent: #7ef0c8;
        --accent-2: #7db4ff;
        --danger: #ff8c93;
        --shadow: 0 28px 80px rgba(0, 0, 0, 0.34);
      }

      * {
        box-sizing: border-box;
      }

      html,
      body {
        margin: 0;
        min-height: 100%;
        background:
          radial-gradient(circle at top left, rgba(125, 180, 255, 0.16), transparent 26%),
          radial-gradient(circle at 82% 12%, rgba(126, 240, 200, 0.15), transparent 24%),
          linear-gradient(180deg, #08101c 0%, #060910 100%);
        color: var(--text);
        font-family: "Space Grotesk", sans-serif;
      }

      body::before {
        content: "";
        position: fixed;
        inset: 0;
        background-image:
          linear-gradient(rgba(255, 255, 255, 0.035) 1px, transparent 1px),
          linear-gradient(90deg, rgba(255, 255, 255, 0.035) 1px, transparent 1px);
        background-size: 72px 72px;
        mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.6), transparent 80%);
        pointer-events: none;
      }

      body.ready .shell,
      body.ready .surface {
        opacity: 1;
        transform: translateY(0);
      }

      .shell {
        width: min(1280px, calc(100vw - 32px));
        margin: 0 auto;
        padding: 28px 0 32px;
        opacity: 0;
        transform: translateY(18px);
        transition: opacity 420ms ease, transform 420ms ease;
      }

      .masthead {
        display: grid;
        gap: 18px;
        padding: 0 0 24px;
        border-bottom: 1px solid var(--line);
      }

      .eyebrow {
        margin: 0 0 10px;
        color: var(--accent);
        letter-spacing: 0.2em;
        text-transform: uppercase;
        font: 500 0.78rem/1.4 "IBM Plex Mono", monospace;
      }

      h1 {
        margin: 0;
        max-width: 12ch;
        font-size: clamp(2.7rem, 6vw, 5rem);
        line-height: 0.92;
        letter-spacing: -0.04em;
      }

      .subtitle {
        margin: 14px 0 0;
        max-width: 52ch;
        color: var(--muted);
        font-size: 1rem;
        line-height: 1.6;
      }

      .target-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 12px;
      }

      .target-item {
        padding: 16px 18px;
        border: 1px solid var(--line);
        background: rgba(10, 14, 22, 0.52);
        backdrop-filter: blur(18px);
      }

      .target-label {
        margin: 0 0 10px;
        color: var(--muted);
        text-transform: uppercase;
        letter-spacing: 0.14em;
        font: 500 0.72rem/1 "IBM Plex Mono", monospace;
      }

      .target-value {
        margin: 0;
        word-break: break-word;
        font-size: 0.98rem;
        line-height: 1.45;
      }

      .workspace {
        display: grid;
        grid-template-columns: minmax(360px, 0.9fr) minmax(420px, 1.1fr);
        gap: 18px;
        margin-top: 22px;
      }

      .surface {
        min-height: 100%;
        border: 1px solid var(--line);
        background: var(--panel);
        box-shadow: var(--shadow);
        backdrop-filter: blur(20px);
        opacity: 0;
        transform: translateY(18px);
        transition:
          opacity 520ms ease,
          transform 520ms ease,
          border-color 200ms ease,
          box-shadow 200ms ease;
      }

      .surface:nth-child(2) {
        transition-delay: 70ms;
      }

      .surface-head {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 16px;
        padding: 20px 22px 18px;
        border-bottom: 1px solid var(--line);
      }

      .surface-title {
        margin: 0;
        font-size: 1.1rem;
      }

      .surface-note,
      .status-line,
      .caption,
      .field-note {
        color: var(--muted);
        font: 500 0.8rem/1.55 "IBM Plex Mono", monospace;
      }

      .surface-body {
        padding: 22px;
      }

      .form-grid {
        display: grid;
        gap: 16px;
      }

      .split {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 14px;
      }

      label {
        display: grid;
        gap: 8px;
        color: var(--text);
        font-size: 0.92rem;
      }

      .label-row {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        gap: 12px;
      }

      input,
      select,
      textarea,
      button {
        font: inherit;
      }

      input,
      select,
      textarea {
        width: 100%;
        padding: 14px 14px 13px;
        border: 1px solid rgba(157, 176, 204, 0.2);
        background: rgba(6, 10, 18, 0.78);
        color: var(--text);
        outline: none;
        transition: border-color 160ms ease, background 160ms ease, transform 160ms ease;
      }

      input:focus,
      select:focus,
      textarea:focus {
        border-color: var(--line-strong);
        background: rgba(8, 12, 20, 0.96);
        transform: translateY(-1px);
      }

      textarea {
        min-height: 148px;
        resize: vertical;
      }

      .prompt-strip {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
      }

      .prompt-chip,
      .ghost-button {
        padding: 10px 12px;
        border: 1px solid rgba(157, 176, 204, 0.18);
        background: transparent;
        color: var(--text);
        cursor: pointer;
        transition:
          border-color 160ms ease,
          color 160ms ease,
          background 160ms ease,
          transform 160ms ease;
      }

      .prompt-chip:hover,
      .ghost-button:hover {
        border-color: var(--line-strong);
        color: var(--accent);
        transform: translateY(-1px);
      }

      .actions {
        display: flex;
        gap: 12px;
        align-items: center;
        justify-content: space-between;
        padding-top: 6px;
      }

      .submit-button {
        position: relative;
        min-width: 180px;
        padding: 15px 18px;
        border: none;
        background: linear-gradient(135deg, var(--accent) 0%, var(--accent-2) 100%);
        color: #08101c;
        font-weight: 700;
        cursor: pointer;
        overflow: hidden;
      }

      .submit-button::after {
        content: "";
        position: absolute;
        inset: 0;
        background: linear-gradient(120deg, transparent 0%, rgba(255, 255, 255, 0.42) 50%, transparent 100%);
        transform: translateX(-140%);
      }

      .submit-button.busy::after {
        animation: sweep 1.2s linear infinite;
      }

      @keyframes sweep {
        to {
          transform: translateX(140%);
        }
      }

      .telemetry-stack {
        display: grid;
        gap: 16px;
      }

      .result-block {
        padding: 18px;
        border: 1px solid rgba(157, 176, 204, 0.16);
        background: var(--panel-strong);
        transition: border-color 180ms ease, box-shadow 180ms ease, transform 180ms ease;
      }

      .surface.has-result .result-block {
        border-color: var(--line-strong);
        box-shadow: inset 0 0 0 1px rgba(126, 240, 200, 0.08);
      }

      .result-label {
        margin: 0 0 10px;
        color: var(--muted);
        text-transform: uppercase;
        letter-spacing: 0.16em;
        font: 500 0.72rem/1 "IBM Plex Mono", monospace;
      }

      .assistant-text {
        min-height: 76px;
        margin: 0;
        font-size: 1rem;
        line-height: 1.7;
        white-space: pre-wrap;
      }

      pre {
        margin: 0;
        white-space: pre-wrap;
        word-break: break-word;
        font: 500 0.81rem/1.65 "IBM Plex Mono", monospace;
        color: #c8d8f4;
      }

      .status-line.error {
        color: var(--danger);
      }

      .footer-note {
        margin-top: 14px;
        color: var(--muted);
        font-size: 0.86rem;
        line-height: 1.7;
      }

      @media (max-width: 980px) {
        .target-grid,
        .workspace,
        .split {
          grid-template-columns: 1fr;
        }

        .shell {
          width: min(100vw - 18px, 100%);
          padding-top: 18px;
        }

        .surface-head,
        .surface-body {
          padding-left: 16px;
          padding-right: 16px;
        }

        .actions {
          flex-direction: column;
          align-items: stretch;
        }

        .submit-button {
          width: 100%;
        }
      }
    </style>
  </head>
  <body>
    <div class="shell">
      <header class="masthead">
        <div>
          <p class="eyebrow">Vertex AI Agent Engine console</p>
          <h1>{{ page.title }}</h1>
          <p class="subtitle">
            A Cloud Run test surface for the current Tailmate agent. The browser only talks to this page.
            Vertex AI calls stay server-side through ADC so no cloud credentials are exposed to the client.
          </p>
        </div>
        <div class="target-grid">
          <section class="target-item">
            <p class="target-label">Project</p>
            <p class="target-value">{{ page.project_id }}</p>
          </section>
          <section class="target-item">
            <p class="target-label">Region</p>
            <p class="target-value">{{ page.location }}</p>
          </section>
          <section class="target-item">
            <p class="target-label">Service</p>
            <p class="target-value">{{ page.service_name }}</p>
          </section>
          <section class="target-item">
            <p class="target-label">Reasoning Engine</p>
            <p class="target-value">{{ page.agent_short_name }}</p>
          </section>
        </div>
      </header>

      <main class="workspace">
        <section class="surface">
          <div class="surface-head">
            <div>
              <h2 class="surface-title">Compose a request</h2>
              <p class="surface-note">Send plain text or attach a media file to exercise the strip-metadata flow.</p>
            </div>
            <p class="caption">Upload cap: {{ page.max_upload_megabytes }} MB</p>
          </div>
          <div class="surface-body">
            <form id="query-form" class="form-grid">
              <div class="split">
                <label>
                  <span class="label-row">
                    <span>Session ID</span>
                    <button class="ghost-button" id="regen-session" type="button">Regenerate</button>
                  </span>
                  <input id="session-id" name="session_id" autocomplete="off">
                </label>
                <label>
                  <span class="label-row">
                    <span>Dog ID</span>
                    <span class="field-note">Optional but recommended</span>
                  </span>
                  <input id="dog-id" name="dog_id" value="{{ page.default_dog_id }}" autocomplete="off">
                </label>
              </div>

              <label>
                <span class="label-row">
                  <span>Trusted User ID</span>
                  <span class="field-note">Optional internal test override</span>
                </span>
                <input id="user-id" name="user_id" value="{{ page.default_user_id }}" autocomplete="off">
              </label>

              <label>
                <span class="label-row">
                  <span>Message</span>
                  <span class="field-note">Used for dog profile turns and fallback upload intent</span>
                </span>
                <textarea id="message" name="message">{{ page.default_message }}</textarea>
              </label>

              <div class="prompt-strip" aria-label="Prompt presets">
                <button class="prompt-chip" type="button" data-prompt="My dog is Peanut.">Create profile</button>
                <button class="prompt-chip" type="button" data-prompt="Peanut is a corgi, 3 years old, and weighs 14 kilograms.">Enrich profile</button>
                <button class="prompt-chip" type="button" data-prompt="Please sanitize and store this upload.">Sanitize upload</button>
              </div>

              <div class="split">
                <label>
                  <span class="label-row">
                    <span>Media upload</span>
                    <span class="field-note">Optional</span>
                  </span>
                  <input id="file" name="file" type="file" accept="image/*,video/*,audio/*">
                </label>
                <label>
                  <span class="label-row">
                    <span>Resource kind</span>
                    <span class="field-note">Auto infers image, video, or audio</span>
                  </span>
                  <select id="resource-kind" name="resource_kind">
                    <option value="auto">Auto</option>
                    <option value="images">Images</option>
                    <option value="videos">Videos</option>
                    <option value="audio">Audio</option>
                  </select>
                </label>
              </div>

              <div class="actions">
                <p class="status-line" id="status-line">Ready to query {{ page.agent_short_name }}.</p>
                <button class="submit-button" id="submit-button" type="submit">Send to Vertex AI</button>
              </div>
            </form>
            <p class="footer-note">
              If you attach a file and leave the message empty, the service falls back to a sanitize-and-store prompt automatically.
            </p>
          </div>
        </section>

        <section class="surface" id="result-surface">
          <div class="surface-head">
            <div>
              <h2 class="surface-title">Response workspace</h2>
              <p class="surface-note">Assistant text, metadata, and raw JSON are shown side by side for smoke testing.</p>
            </div>
            <p class="caption" id="latency">No request yet</p>
          </div>
          <div class="surface-body">
            <div class="telemetry-stack">
              <section class="result-block">
                <p class="result-label">Assistant response</p>
                <p class="assistant-text" id="assistant-text">The next successful query will appear here.</p>
              </section>
              <section class="result-block">
                <p class="result-label">Metadata</p>
                <pre id="metadata-json">{
  "status": "idle"
}</pre>
              </section>
              <section class="result-block">
                <p class="result-label">Raw JSON</p>
                <pre id="raw-json">{
  "status": "idle"
}</pre>
              </section>
            </div>
          </div>
        </section>
      </main>
    </div>

    <script>
      const body = document.body;
      const form = document.getElementById("query-form");
      const sessionInput = document.getElementById("session-id");
      const messageInput = document.getElementById("message");
      const fileInput = document.getElementById("file");
      const statusLine = document.getElementById("status-line");
      const submitButton = document.getElementById("submit-button");
      const resultSurface = document.getElementById("result-surface");
      const assistantText = document.getElementById("assistant-text");
      const metadataJson = document.getElementById("metadata-json");
      const rawJson = document.getElementById("raw-json");
      const latencyLabel = document.getElementById("latency");
      const promptButtons = document.querySelectorAll("[data-prompt]");
      const regenSessionButton = document.getElementById("regen-session");

      const createSessionId = () => {
        if (window.crypto && window.crypto.randomUUID) {
          return "session-" + window.crypto.randomUUID().slice(0, 8);
        }
        return "session-" + Math.random().toString(16).slice(2, 10);
      };

      const setIdleSessionId = () => {
        if (!sessionInput.value.trim()) {
          sessionInput.value = createSessionId();
        }
      };

      const setStatus = (text, isError = false) => {
        statusLine.textContent = text;
        statusLine.classList.toggle("error", isError);
      };

      const consumeSseResponse = async (response, onEvent) => {
        if (!response.body) {
          throw new Error("The streaming response body was empty.");
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let eventName = "message";
        let dataLines = [];

        const dispatch = () => {
          if (!dataLines.length) {
            return;
          }
          const payload = JSON.parse(dataLines.join("\n"));
          onEvent(eventName, payload);
          eventName = "message";
          dataLines = [];
        };

        while (true) {
          const { done, value } = await reader.read();
          buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
          let newlineIndex = buffer.indexOf("\n");
          while (newlineIndex !== -1) {
            let line = buffer.slice(0, newlineIndex);
            buffer = buffer.slice(newlineIndex + 1);
            if (line.endsWith("\r")) {
              line = line.slice(0, -1);
            }
            if (!line) {
              dispatch();
              newlineIndex = buffer.indexOf("\n");
              continue;
            }
            if (line.startsWith("event:")) {
              eventName = line.slice(6).trim();
            } else if (line.startsWith("data:")) {
              dataLines.push(line.slice(5).trimStart());
            }
            newlineIndex = buffer.indexOf("\n");
          }
          if (done) {
            if (buffer.trim()) {
              dataLines.push(buffer.trim());
            }
            dispatch();
            break;
          }
        }
      };

      const renderCompletedResponse = (agentResponse, requestPreview, uploadInfo) => {
        const safeResponse = agentResponse && typeof agentResponse === "object" ? agentResponse : {};
        const responseText = typeof safeResponse.response === "string" ? safeResponse.response : "";
        const responseMetadata = safeResponse.metadata && typeof safeResponse.metadata === "object"
          ? safeResponse.metadata
          : {};
        const responseError = safeResponse.error || null;

        rawJson.textContent = JSON.stringify(
          {
            request_preview: requestPreview,
            upload: uploadInfo || null,
            response: safeResponse,
          },
          null,
          2
        );
        metadataJson.textContent = JSON.stringify(
          {
            request_preview: requestPreview,
            upload: uploadInfo || null,
            metadata: responseMetadata,
            error: responseError,
          },
          null,
          2
        );
        assistantText.textContent = responseText || "The agent returned an empty response.";
        resultSurface.classList.add("has-result");
        if (responseError) {
          setStatus("The agent returned a structured error.", true);
        } else {
          setStatus("Query completed successfully.");
        }
      };

      promptButtons.forEach((button) => {
        button.addEventListener("click", () => {
          messageInput.value = button.dataset.prompt || "";
          messageInput.focus();
        });
      });

      regenSessionButton.addEventListener("click", () => {
        sessionInput.value = createSessionId();
      });

      fileInput.addEventListener("change", () => {
        const file = fileInput.files && fileInput.files[0];
        if (!file) {
          setStatus("Ready to query {{ page.agent_short_name }}.");
          return;
        }
        setStatus("Selected " + file.name + " (" + Math.round(file.size / 1024) + " KB).");
      });

      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        setIdleSessionId();
        const startedAt = performance.now();
        submitButton.disabled = true;
        submitButton.classList.add("busy");
        setStatus("Sending request to Vertex AI...");

        try {
          const response = await fetch("/api/query", {
            method: "POST",
            headers: {
              Accept: "text/event-stream",
            },
            body: new FormData(form),
          });

          if ((response.headers.get("content-type") || "").includes("text/event-stream")) {
            let requestPreview = null;
            let uploadInfo = null;
            assistantText.textContent = "";
            metadataJson.textContent = "{\n  \"status\": \"streaming\"\n}";
            rawJson.textContent = "{\n  \"status\": \"streaming\"\n}";
            setStatus("Streaming response from Vertex AI...");

            await consumeSseResponse(response, (eventName, payload) => {
              if (eventName === "query.context") {
                requestPreview = payload.request_preview || null;
                uploadInfo = payload.upload || null;
                metadataJson.textContent = JSON.stringify(
                  {
                    request_preview: requestPreview,
                    upload: uploadInfo,
                    status: "streaming",
                  },
                  null,
                  2
                );
                rawJson.textContent = JSON.stringify(payload, null, 2);
                resultSurface.classList.add("has-result");
                return;
              }

              if (eventName === "query.started") {
                setStatus("Vertex AI started streaming the answer...");
                return;
              }

              if (eventName === "query.delta") {
                assistantText.textContent += payload.delta || "";
                resultSurface.classList.add("has-result");
                return;
              }

              if (eventName === "query.completed") {
                renderCompletedResponse(payload.output, requestPreview, uploadInfo);
                latencyLabel.textContent = Math.round(performance.now() - startedAt) + " ms";
                rawJson.textContent = JSON.stringify(
                  {
                    request_preview: requestPreview,
                    upload: uploadInfo,
                    event: payload,
                  },
                  null,
                  2
                );
              }
            });
            if (!latencyLabel.textContent || latencyLabel.textContent === "No request yet") {
              latencyLabel.textContent = Math.round(performance.now() - startedAt) + " ms";
            }
            return;
          }

          const data = await response.json();
          const completedAt = performance.now();
          latencyLabel.textContent = Math.round(completedAt - startedAt) + " ms";
          rawJson.textContent = JSON.stringify(data, null, 2);
          resultSurface.classList.add("has-result");

          if (!response.ok) {
            assistantText.textContent = data.error || "The request failed.";
            metadataJson.textContent = JSON.stringify(data, null, 2);
            setStatus("Request failed.", true);
            return;
          }

          const agentResponse = data.response || {};
          assistantText.textContent = agentResponse.response || "The agent returned an empty response.";
          metadataJson.textContent = JSON.stringify(
            {
              request_preview: data.request_preview,
              upload: data.upload || null,
              metadata: agentResponse.metadata || {},
              error: agentResponse.error || null,
            },
            null,
            2
          );
          if (agentResponse.error) {
            setStatus("The agent returned a structured error.", true);
          } else {
            setStatus("Query completed successfully.");
          }
        } catch (error) {
          assistantText.textContent = error instanceof Error ? error.message : String(error);
          metadataJson.textContent = JSON.stringify({ error: assistantText.textContent }, null, 2);
          rawJson.textContent = metadataJson.textContent;
          latencyLabel.textContent = "Request failed";
          resultSurface.classList.add("has-result");
          setStatus("Network or server error.", true);
        } finally {
          submitButton.disabled = false;
          submitButton.classList.remove("busy");
        }
      });

      setIdleSessionId();
      window.requestAnimationFrame(() => body.classList.add("ready"));
    </script>
  </body>
</html>
"""


@dataclass(frozen=True)
class VertexTestUiConfig:
    """Configuration for the Cloud Run Vertex AI test UI."""

    project_id: str
    location: str
    agent_resource_name: str
    service_name: str = "tailmate-vertex-test-ui"
    page_title: str = "Tailmate Vertex Console"
    default_dog_id: str = ""
    default_user_id: str = ""
    default_message: str = DEFAULT_TEXT_PROMPT
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES

    @property
    def max_upload_megabytes(self) -> int:
        return max(1, self.max_upload_bytes // (1024 * 1024))

    @property
    def agent_short_name(self) -> str:
        return self.agent_resource_name.rstrip("/").split("/")[-1]

    @classmethod
    def from_env(cls) -> "VertexTestUiConfig":
        project_id = os.getenv("TAILMATE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
        if not project_id:
            raise RuntimeError("TAILMATE_PROJECT_ID or GOOGLE_CLOUD_PROJECT is required.")

        location = (
            os.getenv("TAILMATE_LOCATION")
            or os.getenv("GOOGLE_CLOUD_LOCATION")
            or os.getenv("CLOUD_ML_REGION")
        )
        if not location:
            raise RuntimeError(
                "TAILMATE_LOCATION, GOOGLE_CLOUD_LOCATION, or CLOUD_ML_REGION is required."
            )

        agent_resource_name = os.getenv("TAILMATE_AGENT_ENGINE_RESOURCE_NAME")
        if not agent_resource_name:
            raise RuntimeError("TAILMATE_AGENT_ENGINE_RESOURCE_NAME is required.")

        raw_max_upload_bytes = os.getenv("TAILMATE_TEST_UI_MAX_UPLOAD_BYTES")
        max_upload_bytes = DEFAULT_MAX_UPLOAD_BYTES
        if raw_max_upload_bytes:
            max_upload_bytes = int(raw_max_upload_bytes)
            if max_upload_bytes <= 0:
                raise RuntimeError("TAILMATE_TEST_UI_MAX_UPLOAD_BYTES must be greater than zero.")

        return cls(
            project_id=project_id,
            location=location,
            agent_resource_name=agent_resource_name,
            service_name=os.getenv("K_SERVICE", "tailmate-vertex-test-ui"),
            page_title=os.getenv("TAILMATE_TEST_UI_TITLE", "Tailmate Vertex Console"),
            default_dog_id=os.getenv("TAILMATE_TEST_UI_DEFAULT_DOG_ID", ""),
            default_user_id=os.getenv("TAILMATE_TEST_UI_USER_ID", ""),
            default_message=os.getenv("TAILMATE_TEST_UI_DEFAULT_MESSAGE", DEFAULT_TEXT_PROMPT),
            max_upload_bytes=max_upload_bytes,
        )


def create_query_payload() -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Build the Agent Engine request payload from the current HTTP request."""

    session_id = (request.form.get("session_id") or f"session-{uuid4().hex[:8]}").strip()
    dog_id = (request.form.get("dog_id") or "").strip()
    user_id = (request.form.get("user_id") or "").strip()
    message = (request.form.get("message") or "").strip()
    metadata: dict[str, Any] = {}
    upload_info: dict[str, Any] | None = None
    uploaded_file = request.files.get("file")

    if dog_id:
        metadata["dog_id"] = dog_id
    if user_id:
        metadata["user_id"] = user_id

    if uploaded_file is not None and uploaded_file.filename:
        raw_bytes = uploaded_file.read()
        if not raw_bytes:
            raise ValueError("Uploaded file is empty.")
        filename = uploaded_file.filename
        content_type = (
            uploaded_file.mimetype
            or mimetypes.guess_type(filename)[0]
            or "application/octet-stream"
        )
        requested_resource_kind = (request.form.get("resource_kind") or "auto").strip() or "auto"
        resource_kind = resolve_resource_kind(requested_resource_kind, content_type)
        upload_limit = resolve_media_upload_limit(
            content_type,
            max_upload_bytes=current_app.config.get("MAX_CONTENT_LENGTH"),
        )
        if len(raw_bytes) > upload_limit:
            raise RequestEntityTooLarge()
        strip_request = normalize_strip_metadata_request(
            {
                "dog_id": dog_id or "demo-dog",
                "resource_kind": resource_kind,
                "filename": filename,
                "content_type": content_type,
                "payload_base64": base64.b64encode(raw_bytes).decode("utf-8"),
                "session_id": session_id,
            }
        )
        metadata[STRIP_METADATA_REQUEST_METADATA_KEY] = strip_request
        upload_info = {
            "filename": strip_request["filename"],
            "content_type": strip_request["content_type"],
            "resource_kind": strip_request["resource_kind"],
            "bytes_uploaded": len(raw_bytes),
        }
        if not message:
            message = DEFAULT_UPLOAD_PROMPT

    if not message:
        raise ValueError("Message is required unless an upload is provided.")
    message = normalize_query_message(message)

    return {
        "session_id": session_id,
        "message": message,
        "metadata": metadata,
    }, upload_info


def resolve_resource_kind(requested_resource_kind: str, content_type: str) -> str:
    """Resolve a user-selected or inferred resource kind."""

    normalized = requested_resource_kind.lower()
    if normalized == "auto":
        if content_type.startswith("audio/"):
            return "audio"
        return "videos" if content_type.startswith("video/") else "images"
    if normalized not in {"images", "videos", "audio"}:
        raise ValueError("resource_kind must be one of: auto, images, videos, audio.")
    return normalized


def redact_query_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a client-safe preview of the request payload."""

    preview: dict[str, Any] = {
        "session_id": payload["session_id"],
        "message": payload["message"],
        "metadata": dict(payload.get("metadata", {})),
    }
    strip_request = preview["metadata"].get(STRIP_METADATA_REQUEST_METADATA_KEY)
    if isinstance(strip_request, dict) and "payload_base64" in strip_request:
        strip_request["payload_base64"] = "<redacted>"
    return preview


def query_agent(
    config: VertexTestUiConfig,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Execute a non-streaming Agent Engine query."""

    client = vertexai.Client(project=config.project_id, location=config.location)
    remote_agent = client.agent_engines.get(name=config.agent_resource_name)
    response = remote_agent.query(input=payload)
    if isinstance(response, dict):
        return response
    raise RuntimeError("The Agent Engine response was not JSON-serializable.")


def stream_query_agent(
    config: VertexTestUiConfig,
    payload: dict[str, Any],
) -> Iterator[dict[str, Any]]:
    """Execute a streaming Agent Engine query."""

    client = vertexai.Client(project=config.project_id, location=config.location)
    remote_agent = client.agent_engines.get(name=config.agent_resource_name)
    response = remote_agent.stream_query(input=payload)
    for chunk in response:
        if isinstance(chunk, dict):
            yield chunk
            continue
        raise RuntimeError("The Agent Engine streaming response was not JSON-serializable.")


def format_sse_event(payload: dict[str, Any], *, event: str | None = None) -> str:
    """Format a JSON payload as a single SSE event."""

    lines: list[str] = []
    event_name = event or str(payload.get("event", "message"))
    if event_name:
        lines.append(f"event: {event_name}")
    lines.append("data: " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return "\n".join(lines) + "\n\n"


def run_health_checks(config: VertexTestUiConfig) -> tuple[dict[str, str], dict[str, str]]:
    """Run the deep health checks exposed by the Cloud Run UI surface."""

    checks: dict[str, str] = {}
    errors: dict[str, str] = {}

    gateway_url = (os.getenv("TAILMATE_DB_GATEWAY_URL") or "").strip()
    if gateway_url:
        gateway_timeout_seconds = int(os.getenv("TAILMATE_DB_GATEWAY_TIMEOUT_SECONDS", "30"))
        gateway_health_url = f"{gateway_url.rstrip('/')}/health"
        try:
            response = requests.get(gateway_health_url, timeout=gateway_timeout_seconds)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or payload.get("status") != "ok":
                raise RuntimeError("DB gateway health endpoint returned an unhealthy payload.")
            checks["db_gateway"] = "ok"
        except Exception as exc:
            checks["db_gateway"] = "error"
            errors["db_gateway"] = str(exc)
    else:
        checks["db_gateway"] = "skipped"

    media_bucket = (os.getenv("TAILMATE_MEDIA_BUCKET") or "").strip()
    if media_bucket:
        blob_name = f"healthchecks/{config.service_name}-{uuid4().hex}.txt"
        blob = storage.Client(project=config.project_id).bucket(media_bucket).blob(blob_name)
        try:
            blob.upload_from_string(b"ok", content_type="text/plain")
            blob.delete()
            checks["gcs"] = "ok"
        except Exception as exc:
            checks["gcs"] = "error"
            errors["gcs"] = str(exc)
    else:
        checks["gcs"] = "skipped"

    return checks, errors


def create_app(config: VertexTestUiConfig | None = None) -> Flask:
    """Create the Flask application used by Cloud Run."""

    runtime_config = config or VertexTestUiConfig.from_env()
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = runtime_config.max_upload_bytes
    app.config["TAILMATE_TEST_UI_CONFIG"] = runtime_config
    app.config["QUERY_AGENT_HANDLER"] = query_agent
    app.config["STREAM_QUERY_AGENT_HANDLER"] = stream_query_agent
    app.config["HEALTH_CHECK_HANDLER"] = run_health_checks

    @app.get("/")
    def index():
        return render_template_string(
            PAGE_TEMPLATE,
            page={
                "title": runtime_config.page_title,
                "project_id": runtime_config.project_id,
                "location": runtime_config.location,
                "service_name": runtime_config.service_name,
                "agent_short_name": runtime_config.agent_short_name,
                "default_dog_id": runtime_config.default_dog_id,
                "default_user_id": runtime_config.default_user_id,
                "default_message": runtime_config.default_message,
                "max_upload_megabytes": runtime_config.max_upload_megabytes,
            },
        )

    @app.get("/statusz")
    @app.get("/healthz")
    def healthz():
        checks, errors = current_app.config["HEALTH_CHECK_HANDLER"](runtime_config)
        status_code = 200 if not errors else 503
        payload = {
            "status": "ok" if status_code == 200 else "error",
            "checks": checks,
            "project_id": runtime_config.project_id,
            "location": runtime_config.location,
            "agent_resource_name": runtime_config.agent_resource_name,
        }
        if errors:
            payload["errors"] = errors
        return jsonify(payload), status_code

    @app.errorhandler(413)
    def payload_too_large(_error):
        return (
            jsonify(
                {
                    "error": (
                        "Uploaded file is too large for this test surface. "
                        f"Current limit: {runtime_config.max_upload_bytes} bytes."
                    )
                }
            ),
            413,
        )

    @app.post("/api/query")
    def api_query():
        try:
            payload, upload_info = create_query_payload()
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        query_handler = current_app.config["QUERY_AGENT_HANDLER"]
        wants_stream = "text/event-stream" in request.headers.get("Accept", "").lower()
        try:
            if wants_stream:
                stream_handler = current_app.config["STREAM_QUERY_AGENT_HANDLER"]

                def _stream_response() -> Iterator[str]:
                    try:
                        yield format_sse_event(
                            {
                                "event": "query.context",
                                "request_preview": redact_query_payload(payload),
                                "upload": upload_info,
                            }
                        )
                        for event in stream_handler(runtime_config, payload):
                            if not isinstance(event, dict):
                                raise RuntimeError(
                                    "The Agent Engine streaming response was not JSON-serializable."
                                )
                            proxied_event = dict(event)
                            output = proxied_event.get("output")
                            if isinstance(output, dict):
                                proxied_event["output"] = dict(output)
                            yield format_sse_event(proxied_event)
                    except Exception:
                        yield format_sse_event(
                            {
                                "event": "query.completed",
                                "output": {
                                    "session_id": payload["session_id"],
                                    "response": "",
                                    "metadata": {},
                                    "error": InternalError().to_error_detail(),
                                },
                            }
                        )

                response = Response(
                    stream_with_context(_stream_response()),
                    mimetype="text/event-stream",
                )
                response.headers["Cache-Control"] = "no-cache"
                response.headers["X-Accel-Buffering"] = "no"
                return response
            response = query_handler(runtime_config, payload)
        except Exception as exc:
            return jsonify({"error": f"Agent Engine query failed: {exc}"}), 502

        return jsonify(
            {
                "response": response,
                "request_preview": redact_query_payload(payload),
                "upload": upload_info,
            }
        )

    return app
