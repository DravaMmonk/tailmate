"""Deployment entrypoint."""

from contextlib import contextmanager
from importlib import metadata as importlib_metadata
import json
import os
from pathlib import Path
import shutil
import sys
import tomllib

import vertexai
from vertexai import types
from vertexai._genai import _agent_engines_utils

from tailmate.adapters.vertex_agent_engine.agent_app import create_agent_app
from tailmate.bootstrap.config import AppConfig, AppEnvironment

os.environ["TAILMATE_ENV"] = AppEnvironment.CLOUD.value

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PYPROJECT_FILE = PROJECT_ROOT / "pyproject.toml"
DEPLOYMENT_PYTHON_VERSION = "3.11"
DEPLOYMENT_REQUIREMENTS_FILE = PROJECT_ROOT / "deployment" / "agent_engine" / "requirements.txt"
UV_LOCK_FILE = PROJECT_ROOT / "uv.lock"
SOURCE_BUNDLE_ROOT = PROJECT_ROOT / ".agent_engine_build"
SOURCE_DEPLOYMENT_MODE = "source"
OBJECT_DEPLOYMENT_MODE = "object"
DEFAULT_DEPLOYMENT_MODE = SOURCE_DEPLOYMENT_MODE
RESERVED_AGENT_ENGINE_ENV_VARS = {
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_LOCATION",
    "CLOUD_ML_REGION",
    "GOOGLE_APPLICATION_CREDENTIALS",
}
LOCAL_DEPLOYMENT_RUNTIME_PACKAGES = ("cloudpickle", "pydantic", "tailmate-app")
PACKAGE_TREE_NAME = "tailmate"
DEFAULT_DEPLOYMENT_EXTRA_PACKAGES = [PACKAGE_TREE_NAME]
DEFAULT_SOURCE_PACKAGES = ["tailmate", "requirements.txt"]
DEFAULT_NO_PROXY_HOSTS = (
    "127.0.0.1",
    "localhost",
    "169.254.169.254",
    "metadata.google.internal",
)
SOURCE_TREE_IGNORE_PATTERNS = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo")


def load_deployment_requirements() -> list[str]:
    """Load the pinned deployment requirements generated from uv.lock."""

    requirements: list[str] = []
    for raw_line in DEPLOYMENT_REQUIREMENTS_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        requirements.append(line)
    return requirements


def load_locked_python_version() -> str:
    """Return the Python version family pinned in uv.lock."""

    data = tomllib.loads(UV_LOCK_FILE.read_text(encoding="utf-8"))
    requires_python = data["requires-python"]
    return requires_python.removeprefix("==").removesuffix(".*")


def load_project_version() -> str:
    """Return the canonical package version declared in pyproject.toml."""

    data = tomllib.loads(PYPROJECT_FILE.read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def load_required_runtime_versions() -> dict[str, str]:
    """Return exact local package versions required for clean deployment packaging."""

    required_versions: dict[str, str] = {}
    for requirement in load_deployment_requirements():
        requirement_name = requirement.split(";", maxsplit=1)[0].strip()
        if "==" not in requirement_name:
            continue
        package_name, version = requirement_name.split("==", maxsplit=1)
        normalized_name = package_name.strip().lower()
        if normalized_name in LOCAL_DEPLOYMENT_RUNTIME_PACKAGES:
            required_versions[normalized_name] = version.strip()
    return required_versions


@contextmanager
def working_directory(path: Path):
    """Temporarily switch the process working directory."""

    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def get_installed_package_version(package_name: str) -> str | None:
    """Return the installed version for a local package if present."""

    try:
        return importlib_metadata.version(package_name)
    except importlib_metadata.PackageNotFoundError:
        return None


def validate_local_deployment_runtime() -> None:
    """Fail fast when the local deployment runtime drifts from the locked build contract."""

    expected_python = load_locked_python_version()
    current_python = f"{sys.version_info.major}.{sys.version_info.minor}"
    if current_python != expected_python:
        raise RuntimeError(
            "Deployment must run under Python "
            f"{expected_python}, but the current interpreter is {current_python}. "
            "Run `uv sync --python /path/to/python3.11` and invoke deployment with "
            "`uv run --python /path/to/python3.11`."
        )

    required_versions = load_required_runtime_versions()
    mismatches: list[str] = []
    missing: list[str] = []
    for package_name in LOCAL_DEPLOYMENT_RUNTIME_PACKAGES:
        installed_version = get_installed_package_version(package_name)
        if installed_version is None:
            missing.append(package_name)
            continue
        expected_version = required_versions.get(package_name)
        if expected_version and installed_version != expected_version:
            mismatches.append(
                f"{package_name}=={installed_version} (expected {expected_version})"
            )

    if missing or mismatches:
        details: list[str] = []
        if missing:
            details.append(f"missing packages: {', '.join(sorted(missing))}")
        if mismatches:
            details.append(f"version drift: {', '.join(sorted(mismatches))}")
        raise RuntimeError(
            "Local deployment runtime is not clean enough for Agent Engine packaging: "
            + "; ".join(details)
            + ". Rebuild the environment with `uv sync --python /path/to/python3.11`."
        )


def build_private_service_connect_config(
    config: AppConfig,
) -> dict[str, object] | None:
    """Build the user-facing PSC config block for deployment helpers."""

    if config.uses_db_gateway:
        return None
    if not config.network_attachment:
        return None
    psc_config: dict[str, object] = {"network_attachment": config.network_attachment}
    if (
        config.dns_peering_domain
        and config.dns_peering_target_project
        and config.dns_peering_target_network
    ):
        psc_config["dns_peering_configs"] = [
            {
                "domain": config.dns_peering_domain,
                "target_project": config.dns_peering_target_project,
                "target_network": config.dns_peering_target_network,
            }
        ]
    return psc_config


def load_deployment_mode() -> str:
    """Return the requested deployment mode."""

    mode = os.getenv("TAILMATE_AGENT_ENGINE_DEPLOYMENT_MODE", DEFAULT_DEPLOYMENT_MODE).strip().lower()
    if mode not in {SOURCE_DEPLOYMENT_MODE, OBJECT_DEPLOYMENT_MODE}:
        raise RuntimeError(
            "TAILMATE_AGENT_ENGINE_DEPLOYMENT_MODE must be either "
            f"`{SOURCE_DEPLOYMENT_MODE}` or `{OBJECT_DEPLOYMENT_MODE}`."
        )
    return mode


def scrub_reserved_env_vars(env_vars: dict[str, str]) -> dict[str, str]:
    """Drop env vars that are reserved by the managed Agent Engine runtime."""

    cleaned_env_vars: dict[str, str] = {}
    for key, value in env_vars.items():
        if key in RESERVED_AGENT_ENGINE_ENV_VARS or value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        cleaned_env_vars[key] = value
    return cleaned_env_vars


def build_runtime_env_vars(config: AppConfig) -> dict[str, str]:
    """Build the runtime env vars for Agent Engine deployment."""

    no_proxy_entries = list(DEFAULT_NO_PROXY_HOSTS)
    if config.requires_direct_database and config.db_ip:
        no_proxy_entries.append(config.db_ip)
    if config.no_proxy:
        no_proxy_entries.extend(
            [entry.strip() for entry in config.no_proxy.split(",") if entry.strip()]
        )
    no_proxy = ",".join(dict.fromkeys(no_proxy_entries))

    return scrub_reserved_env_vars(
        {
            "TAILMATE_PROJECT_ID": config.tailmate_project_id or config.project_id,
            "TAILMATE_LOCATION": config.tailmate_location or config.location,
            "TAILMATE_ENV": config.environment.value,
            "TAILMATE_AGENT_NAME": config.agent_name,
            "TAILMATE_DB_USER": config.db_user if config.requires_direct_database else None,
            "TAILMATE_DB_PASSWORD": (
                config.db_password.get_secret_value()
                if config.requires_direct_database and config.db_password is not None
                else None
            ),
            "TAILMATE_DB_IP": config.db_ip if config.requires_direct_database else None,
            "TAILMATE_DB_NAME": config.db_name if config.requires_direct_database else None,
            "TAILMATE_DB_CONNECT_TIMEOUT_SECONDS": (
                str(config.db_connect_timeout_seconds) if config.requires_direct_database else None
            ),
            "TAILMATE_DB_SSLMODE": config.db_sslmode if config.requires_direct_database else None,
            "TAILMATE_MEDIA_BUCKET": config.media_bucket or "",
            "TAILMATE_DB_GATEWAY_URL": config.db_gateway_url or "",
            "TAILMATE_DB_GATEWAY_TIMEOUT_SECONDS": (
                str(config.db_gateway_timeout_seconds) if config.uses_db_gateway else ""
            ),
            "TAILMATE_ENABLED_SKILLS": config.enabled_skills_raw or "",
            "TAILMATE_DISABLED_SKILLS": config.disabled_skills_raw or "",
            "TAILMATE_EXTRACTION_STRATEGY": config.extraction_strategy.value,
            "TAILMATE_GEMINI_LOCATION": config.gemini_location,
            "TAILMATE_GEMINI_FLASH_MODEL": config.gemini_flash_model,
            "TAILMATE_GEMINI_PRO_MODEL": config.gemini_pro_model,
            "TAILMATE_GEMINI_TIMEOUT_SECONDS": str(config.gemini_timeout_seconds),
            "TAILMATE_KB_ENABLED": "true" if config.kb_enabled else "false",
            "TAILMATE_EMBEDDING_MODEL": config.embedding_model,
            "TAILMATE_KB_THRESHOLD": str(config.kb_threshold),
            "TAILMATE_NETWORK_ATTACHMENT": (
                (config.network_attachment or "") if not config.uses_db_gateway else ""
            ),
            "TAILMATE_SERVICE_ACCOUNT": config.service_account or "",
            "HTTP_PROXY": config.outbound_proxy_url or "",
            "HTTPS_PROXY": config.outbound_proxy_url or "",
            "NO_PROXY": no_proxy if config.outbound_proxy_url else "",
        }
    )


def build_vertex_agent_engine_config(config: AppConfig) -> types.AgentEngineConfig:
    """Build the Vertex AI SDK deployment config from the canonical app config."""

    kwargs: dict[str, object] = {
        "requirements": load_deployment_requirements(),
        "pythonVersion": DEPLOYMENT_PYTHON_VERSION,
        "envVars": build_runtime_env_vars(config),
    }
    if config.service_account:
        kwargs["serviceAccount"] = config.service_account

    private_service_connect_config = build_private_service_connect_config(config)
    if private_service_connect_config is not None:
        dns_peering_configs = None
        raw_dns_peering_configs = private_service_connect_config.get("dns_peering_configs")
        if isinstance(raw_dns_peering_configs, list):
            dns_peering_configs = [
                types.DnsPeeringConfig(
                    domain=dns_peering_config["domain"],
                    targetProject=dns_peering_config["target_project"],
                    targetNetwork=dns_peering_config["target_network"],
                )
                for dns_peering_config in raw_dns_peering_configs
            ]
        kwargs["pscInterfaceConfig"] = types.PscInterfaceConfig(
            networkAttachment=private_service_connect_config["network_attachment"],
            dnsPeeringConfigs=dns_peering_configs,
        )
    return types.AgentEngineConfig(**kwargs)


def build_validated_vertex_agent_engine_config(config: AppConfig) -> types.AgentEngineConfig:
    """Build the deployment config after enforcing the local runtime contract."""

    validate_local_deployment_runtime()
    return build_vertex_agent_engine_config(config)


def require_deployment_target(name: str) -> str:
    """Require a deployment-time environment variable."""

    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required deployment environment variable: {name}")
    return value


def generate_source_class_methods(agent: object) -> list[dict[str, object]]:
    """Generate the query operation schema used by source-based deployments."""

    operations = _agent_engines_utils._get_registered_operations(agent=agent)
    class_methods = _agent_engines_utils._generate_class_methods_spec_or_raise(
        agent=agent,
        operations=operations,
    )
    return [_agent_engines_utils._to_dict(method) for method in class_methods]


def prepare_source_bundle(
    *,
    bundle_name: str,
    requirements_file: str | None,
) -> tuple[Path, list[str], str | None]:
    """Create a flat, importable source tree for Agent Engine source deployments."""

    bundle_root = SOURCE_BUNDLE_ROOT / bundle_name
    if bundle_root.exists():
        shutil.rmtree(bundle_root)
    bundle_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        PROJECT_ROOT / "src" / PACKAGE_TREE_NAME,
        bundle_root / PACKAGE_TREE_NAME,
        ignore=SOURCE_TREE_IGNORE_PATTERNS,
    )

    source_packages = ["tailmate"]
    bundled_requirements_file: str | None = None
    if requirements_file is not None:
        shutil.copy2(PROJECT_ROOT / requirements_file, bundle_root / "requirements.txt")
        source_packages.append("requirements.txt")
        bundled_requirements_file = "requirements.txt"

    return bundle_root, source_packages, bundled_requirements_file


def prepare_object_bundle(*, bundle_name: str) -> tuple[Path, list[str]]:
    """Create a flat extra-packages tree for pickle-based deployments."""

    bundle_root = SOURCE_BUNDLE_ROOT / bundle_name
    if bundle_root.exists():
        shutil.rmtree(bundle_root)
    bundle_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        PROJECT_ROOT / "src" / PACKAGE_TREE_NAME,
        bundle_root / PACKAGE_TREE_NAME,
        ignore=SOURCE_TREE_IGNORE_PATTERNS,
    )
    return bundle_root, DEFAULT_DEPLOYMENT_EXTRA_PACKAGES.copy()


def build_agent_engine_request_config(
    config: AppConfig,
    *,
    display_name: str,
    description: str,
    staging_bucket: str,
    extra_packages: list[str] | None = None,
) -> types.AgentEngineConfig:
    """Build the full Agent Engine create request config."""

    base = build_validated_vertex_agent_engine_config(config)
    payload = base.model_dump(by_alias=False, exclude_none=True)
    payload.update(
        staging_bucket=staging_bucket,
        display_name=display_name,
        description=description,
        extra_packages=extra_packages or DEFAULT_DEPLOYMENT_EXTRA_PACKAGES,
        agent_framework="custom",
    )
    return types.AgentEngineConfig(**payload)


def build_source_agent_engine_request_config(
    config: AppConfig,
    *,
    agent: object,
    display_name: str,
    description: str,
    entrypoint_module: str,
    entrypoint_object: str,
    source_packages: list[str],
    requirements_file: str | None,
) -> types.AgentEngineConfig:
    """Build a source-based Agent Engine create request config."""

    base = build_validated_vertex_agent_engine_config(config)
    payload = base.model_dump(by_alias=False, exclude_none=True)
    payload.update(
        displayName=display_name,
        description=description,
        sourcePackages=source_packages,
        entrypointModule=entrypoint_module,
        entrypointObject=entrypoint_object,
        classMethods=generate_source_class_methods(agent),
        agentFramework="custom",
    )
    payload.pop("requirements", None)
    if requirements_file is not None:
        payload["requirementsFile"] = requirements_file
    return types.AgentEngineConfig(**payload)


def build_deploy_request_config(
    *,
    agent: object,
    config: AppConfig,
    display_name: str,
    description: str,
    entrypoint_module: str | None,
    entrypoint_object: str | None,
    source_packages: list[str] | None,
    requirements_file: str | None,
    extra_packages: list[str] | None = None,
) -> types.AgentEngineConfig:
    """Select the clean deployment request shape for the configured mode."""

    deployment_mode = load_deployment_mode()
    if deployment_mode == SOURCE_DEPLOYMENT_MODE:
        if not entrypoint_module or not entrypoint_object:
            raise RuntimeError(
                "Source deployments require both `entrypoint_module` and `entrypoint_object`."
            )
        return build_source_agent_engine_request_config(
            config,
            agent=agent,
            display_name=display_name,
            description=description,
            entrypoint_module=entrypoint_module,
            entrypoint_object=entrypoint_object,
            source_packages=source_packages or DEFAULT_SOURCE_PACKAGES,
            requirements_file=requirements_file,
        )

    staging_bucket = require_deployment_target("TAILMATE_AGENT_ENGINE_STAGING_BUCKET")
    return build_agent_engine_request_config(
        config,
        display_name=display_name,
        description=description,
        staging_bucket=staging_bucket,
        extra_packages=extra_packages,
    )


def is_source_deployment_mode() -> bool:
    """Return whether the current deployment uses source packages."""

    return load_deployment_mode() == SOURCE_DEPLOYMENT_MODE


def deploy_agent_engine(
    *,
    agent: object,
    config: AppConfig,
    default_display_name: str,
    default_description: str,
    entrypoint_module: str | None = None,
    entrypoint_object: str | None = None,
    source_packages: list[str] | None = None,
    requirements_file: str | None = "deployment/agent_engine/requirements.txt",
    source_bundle_name: str = "root",
    extra_packages: list[str] | None = None,
) -> types.AgentEngine:
    """Deploy an agent to Vertex AI Agent Engine and print the resource name."""

    display_name = os.getenv("TAILMATE_AGENT_ENGINE_DISPLAY_NAME", default_display_name)
    description = os.getenv("TAILMATE_AGENT_ENGINE_DESCRIPTION", default_description)
    client = vertexai.Client(project=config.project_id, location=config.location)
    if is_source_deployment_mode():
        bundle_root, bundle_source_packages, bundled_requirements_file = prepare_source_bundle(
            bundle_name=source_bundle_name,
            requirements_file=requirements_file,
        )
        with working_directory(bundle_root):
            request_config = build_deploy_request_config(
                agent=agent,
                config=config,
                display_name=display_name,
                description=description,
                entrypoint_module=entrypoint_module,
                entrypoint_object=entrypoint_object,
                source_packages=source_packages or bundle_source_packages,
                requirements_file=bundled_requirements_file,
            )
            remote_agent = client.agent_engines.create(config=request_config)
    else:
        bundle_root, bundle_extra_packages = prepare_object_bundle(bundle_name=source_bundle_name)
        with working_directory(bundle_root):
            request_config = build_deploy_request_config(
                agent=agent,
                config=config,
                display_name=display_name,
                description=description,
                entrypoint_module=entrypoint_module,
                entrypoint_object=entrypoint_object,
                source_packages=source_packages,
                requirements_file=requirements_file,
                extra_packages=extra_packages or bundle_extra_packages,
            )
            remote_agent = client.agent_engines.create(agent=agent, config=request_config)
    resource_name = getattr(getattr(remote_agent, "api_resource", None), "name", None)
    if resource_name is None:
        resource_name = getattr(remote_agent, "name", None)
    if resource_name is None:
        raise RuntimeError(
            "Agent Engine deployment succeeded but the SDK response did not expose a resource name."
        )
    print(json.dumps({"name": resource_name}, indent=2))
    return remote_agent


def main() -> int:
    """Deploy the root Tailmate agent through the clean uv-run contract."""

    version = load_project_version()
    deploy_agent_engine(
        agent=app,
        config=app.config,
        default_display_name=f"tailmate-v{version.replace('.', '-')}",
        default_description=f"Tailmate v{version} custom agent",
        entrypoint_module="tailmate.entrypoints.root_app",
        entrypoint_object="app",
        source_packages=DEFAULT_SOURCE_PACKAGES,
        source_bundle_name="root",
    )
    return 0

app = create_agent_app(environment=AppEnvironment.CLOUD)
AGENT_ENGINE_CONFIG = {
    "requirements": load_deployment_requirements(),
    "python_version": DEPLOYMENT_PYTHON_VERSION,
    "deployment_mode": load_deployment_mode(),
    "database_access_mode": "gateway" if app.config.uses_db_gateway else "direct",
    "private_service_connect_config": build_private_service_connect_config(app.config),
    "env_vars": build_runtime_env_vars(app.config),
    "service_account": app.config.service_account,
}


if __name__ == "__main__":
    raise SystemExit(main())
