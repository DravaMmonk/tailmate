from __future__ import annotations

import importlib
import os
from types import SimpleNamespace

from tailmate.bootstrap.config import AppEnvironment


def test_deploy_entrypoint_forces_cloud_mode(monkeypatch, set_deploy_env, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    set_deploy_env(
        TAILMATE_DB_CONNECT_TIMEOUT_SECONDS="12",
        TAILMATE_DB_SSLMODE="require",
        TAILMATE_ENABLED_SKILLS="dog_profile,strip_metadata",
        TAILMATE_DISABLED_SKILLS="legacy_skill",
        TAILMATE_EXTRACTION_STRATEGY="flash",
        TAILMATE_GEMINI_API_KEY="projects/test/secrets/tailmate-gemini/versions/latest",
        TAILMATE_GEMINI_LOCATION="global",
        TAILMATE_GEMINI_FLASH_MODEL="gemini-2.5-flash",
        TAILMATE_GEMINI_PRO_MODEL="gemini-2.5-pro",
        TAILMATE_GEMINI_TIMEOUT_SECONDS="20",
        TAILMATE_KB_ENABLED="true",
        TAILMATE_EMBEDDING_MODEL="text-embedding-004",
        TAILMATE_KB_THRESHOLD="0.82",
        TAILMATE_SERVICE_ACCOUNT="tailmate-agent@test.iam.gserviceaccount.com",
        TAILMATE_OUTBOUND_PROXY_URL="http://10.0.0.20:8888",
        TAILMATE_DNS_PEERING_DOMAIN=None,
        TAILMATE_DNS_PEERING_TARGET_PROJECT=None,
        TAILMATE_DNS_PEERING_TARGET_NETWORK=None,
    )

    deploy = importlib.import_module("tailmate.entrypoints.deploy")

    assert os.environ["TAILMATE_ENV"] == "CLOUD"
    assert deploy.app.config.environment is AppEnvironment.CLOUD
    assert deploy.DEPLOYMENT_PYTHON_VERSION == "3.11"
    assert deploy.load_locked_python_version() == "3.11"
    assert deploy.load_project_version() == "0.8.0"
    assert deploy.AGENT_ENGINE_CONFIG["deployment_mode"] == "source"
    assert deploy.AGENT_ENGINE_CONFIG["private_service_connect_config"] == {
        "network_attachment": "projects/test/regions/us-central1/networkAttachments/tailmate",
    }
    assert deploy.AGENT_ENGINE_CONFIG["env_vars"]["TAILMATE_PROJECT_ID"] == "test-project"
    assert deploy.AGENT_ENGINE_CONFIG["env_vars"]["TAILMATE_LOCATION"] == "us-central1"
    assert deploy.AGENT_ENGINE_CONFIG["env_vars"]["TAILMATE_DB_CONNECT_TIMEOUT_SECONDS"] == "12"
    assert deploy.AGENT_ENGINE_CONFIG["env_vars"]["TAILMATE_DB_SSLMODE"] == "require"
    assert (
        deploy.AGENT_ENGINE_CONFIG["env_vars"]["TAILMATE_ENABLED_SKILLS"]
        == "dog_profile,strip_metadata"
    )
    assert deploy.AGENT_ENGINE_CONFIG["env_vars"]["TAILMATE_DISABLED_SKILLS"] == "legacy_skill"
    assert deploy.AGENT_ENGINE_CONFIG["env_vars"]["TAILMATE_EXTRACTION_STRATEGY"] == "flash"
    assert "TAILMATE_GEMINI_API_KEY" not in deploy.AGENT_ENGINE_CONFIG["env_vars"]
    assert deploy.AGENT_ENGINE_CONFIG["env_vars"]["TAILMATE_GEMINI_LOCATION"] == "global"
    assert deploy.AGENT_ENGINE_CONFIG["env_vars"]["TAILMATE_GEMINI_FLASH_MODEL"] == "gemini-2.5-flash"
    assert deploy.AGENT_ENGINE_CONFIG["env_vars"]["TAILMATE_GEMINI_PRO_MODEL"] == "gemini-2.5-pro"
    assert deploy.AGENT_ENGINE_CONFIG["env_vars"]["TAILMATE_GEMINI_TIMEOUT_SECONDS"] == "20"
    assert deploy.AGENT_ENGINE_CONFIG["env_vars"]["TAILMATE_KB_ENABLED"] == "true"
    assert deploy.AGENT_ENGINE_CONFIG["env_vars"]["TAILMATE_EMBEDDING_MODEL"] == "text-embedding-004"
    assert deploy.AGENT_ENGINE_CONFIG["env_vars"]["TAILMATE_KB_THRESHOLD"] == "0.82"
    assert "GOOGLE_CLOUD_PROJECT" not in deploy.AGENT_ENGINE_CONFIG["env_vars"]
    assert "GOOGLE_CLOUD_LOCATION" not in deploy.AGENT_ENGINE_CONFIG["env_vars"]
    assert deploy.AGENT_ENGINE_CONFIG["env_vars"]["HTTPS_PROXY"] == "http://10.0.0.20:8888"
    assert deploy.AGENT_ENGINE_CONFIG["env_vars"]["NO_PROXY"] == (
        "127.0.0.1,localhost,169.254.169.254,metadata.google.internal,10.0.0.10"
    )
    assert deploy.AGENT_ENGINE_CONFIG["service_account"] == (
        "tailmate-agent@test.iam.gserviceaccount.com"
    )


def test_deploy_entrypoint_adds_dns_peering_only_when_configured(
    monkeypatch,
    set_deploy_env,
    tmp_path,
) -> None:
    monkeypatch.chdir(tmp_path)
    set_deploy_env(
        TAILMATE_DNS_PEERING_DOMAIN="tailmate.internal.",
        TAILMATE_DNS_PEERING_TARGET_PROJECT="test-project",
        TAILMATE_DNS_PEERING_TARGET_NETWORK="default",
    )

    deploy = importlib.import_module("tailmate.entrypoints.deploy")

    assert deploy.AGENT_ENGINE_CONFIG["private_service_connect_config"] == {
        "network_attachment": "projects/test/regions/us-central1/networkAttachments/tailmate",
        "dns_peering_configs": [
            {
                "domain": "tailmate.internal.",
                "target_project": "test-project",
                "target_network": "default",
            }
        ],
    }


def test_validate_local_deployment_runtime_rejects_wrong_python(set_deploy_env, monkeypatch) -> None:
    set_deploy_env()
    deploy = importlib.import_module("tailmate.entrypoints.deploy")
    monkeypatch.setattr(deploy, "load_locked_python_version", lambda: "3.11")
    monkeypatch.setattr(deploy.sys, "version_info", SimpleNamespace(major=3, minor=13))

    try:
        deploy.validate_local_deployment_runtime()
    except RuntimeError as exc:
        assert "Python 3.11" in str(exc)
    else:
        raise AssertionError("validate_local_deployment_runtime() should reject Python drift")


def test_validate_local_deployment_runtime_rejects_missing_or_drifted_packages(
    set_deploy_env,
    monkeypatch,
) -> None:
    set_deploy_env()
    deploy = importlib.import_module("tailmate.entrypoints.deploy")
    monkeypatch.setattr(deploy, "load_locked_python_version", lambda: "3.11")
    monkeypatch.setattr(deploy.sys, "version_info", SimpleNamespace(major=3, minor=11))
    monkeypatch.setattr(
        deploy,
        "load_required_runtime_versions",
        lambda: {
            "cloudpickle": "3.1.2",
            "pydantic": "2.13.0b2",
            "tailmate-app": "0.1.0",
        },
    )
    installed_versions = {
        "cloudpickle": "3.1.1",
        "pydantic": "2.13.0b2",
        "tailmate-app": None,
    }
    monkeypatch.setattr(
        deploy,
        "get_installed_package_version",
        lambda package_name: installed_versions[package_name],
    )

    try:
        deploy.validate_local_deployment_runtime()
    except RuntimeError as exc:
        assert "missing packages: tailmate-app" in str(exc)
        assert "version drift: cloudpickle==3.1.1 (expected 3.1.2)" in str(exc)
    else:
        raise AssertionError("validate_local_deployment_runtime() should reject runtime drift")


def test_build_deploy_request_config_defaults_to_source_packages(
    set_deploy_env,
    monkeypatch,
) -> None:
    set_deploy_env()
    deploy = importlib.import_module("tailmate.entrypoints.deploy")
    monkeypatch.setattr(deploy, "validate_local_deployment_runtime", lambda: None)

    request_config = deploy.build_deploy_request_config(
        agent=deploy.app,
        config=deploy.app.config,
        display_name="tailmate-test",
        description="test",
        entrypoint_module="tailmate.entrypoints.root_app",
        entrypoint_object="app",
        source_packages=deploy.DEFAULT_SOURCE_PACKAGES,
        requirements_file="deployment/agent_engine/requirements.txt",
    ).model_dump(by_alias=False, exclude_none=True)

    assert "staging_bucket" not in request_config
    assert request_config["source_packages"] == deploy.DEFAULT_SOURCE_PACKAGES
    assert request_config["entrypoint_module"] == "tailmate.entrypoints.root_app"
    assert request_config["entrypoint_object"] == "app"
    assert request_config["requirements_file"] == "deployment/agent_engine/requirements.txt"
    assert request_config["class_methods"]


def test_build_runtime_env_vars_drops_empty_optional_values(set_deploy_env, monkeypatch) -> None:
    set_deploy_env()
    monkeypatch.delenv("TAILMATE_SERVICE_ACCOUNT", raising=False)
    monkeypatch.delenv("SERVICE_ACCOUNT", raising=False)
    deploy = importlib.import_module("tailmate.entrypoints.deploy")

    env_vars = deploy.build_runtime_env_vars(deploy.app.config)

    assert "TAILMATE_SERVICE_ACCOUNT" not in env_vars
    assert "HTTP_PROXY" not in env_vars
    assert "HTTPS_PROXY" not in env_vars
    assert "NO_PROXY" not in env_vars
    assert "TAILMATE_GEMINI_API_KEY" not in env_vars
    assert env_vars["TAILMATE_GEMINI_LOCATION"] == "global"
    assert env_vars["TAILMATE_GEMINI_FLASH_MODEL"] == "gemini-2.5-flash"


def test_build_runtime_env_vars_omits_gemini_api_key_when_configured(
    set_deploy_env,
    monkeypatch,
) -> None:
    set_deploy_env(TAILMATE_GEMINI_API_KEY="projects/test/secrets/tailmate-gemini/versions/latest")
    deploy = importlib.import_module("tailmate.entrypoints.deploy")

    env_vars = deploy.build_runtime_env_vars(deploy.app.config)

    assert "TAILMATE_GEMINI_API_KEY" not in env_vars


def test_build_runtime_env_vars_include_knowledge_base_flags(set_deploy_env, monkeypatch) -> None:
    set_deploy_env(
        TAILMATE_KB_ENABLED="true",
        TAILMATE_EMBEDDING_MODEL="text-embedding-004",
        TAILMATE_KB_THRESHOLD="0.9",
    )
    deploy = importlib.import_module("tailmate.entrypoints.deploy")

    env_vars = deploy.build_runtime_env_vars(deploy.app.config)

    assert env_vars["TAILMATE_KB_ENABLED"] == "true"
    assert env_vars["TAILMATE_EMBEDDING_MODEL"] == "text-embedding-004"
    assert env_vars["TAILMATE_KB_THRESHOLD"] == "0.9"


def test_build_runtime_env_vars_omit_direct_database_settings_when_gateway_is_enabled(
    set_deploy_env,
    monkeypatch,
) -> None:
    set_deploy_env(TAILMATE_DB_GATEWAY_URL="https://tailmate-db-gateway-abc.a.run.app")
    deploy = importlib.import_module("tailmate.entrypoints.deploy")

    env_vars = deploy.build_runtime_env_vars(deploy.app.config)

    assert env_vars["TAILMATE_DB_GATEWAY_URL"] == "https://tailmate-db-gateway-abc.a.run.app"
    assert env_vars["TAILMATE_DB_GATEWAY_TIMEOUT_SECONDS"] == "30"
    assert "TAILMATE_DB_USER" not in env_vars
    assert "TAILMATE_DB_PASSWORD" not in env_vars
    assert "TAILMATE_DB_IP" not in env_vars
    assert "TAILMATE_NETWORK_ATTACHMENT" not in env_vars


def test_build_private_service_connect_config_is_disabled_when_gateway_is_enabled(
    set_deploy_env,
    monkeypatch,
) -> None:
    set_deploy_env(TAILMATE_DB_GATEWAY_URL="https://tailmate-db-gateway-abc.a.run.app")
    deploy = importlib.import_module("tailmate.entrypoints.deploy")

    assert deploy.build_private_service_connect_config(deploy.app.config) is None
    assert deploy.AGENT_ENGINE_CONFIG["private_service_connect_config"] is None
    assert deploy.AGENT_ENGINE_CONFIG["database_access_mode"] == "gateway"


def test_prepare_object_bundle_flattens_package_tree(monkeypatch, set_deploy_env, tmp_path) -> None:
    source_root = tmp_path / "project"
    package_root = source_root / "src" / "tailmate"
    cache_root = package_root / "__pycache__"
    cache_root.mkdir(parents=True)
    (package_root / "__init__.py").write_text("", encoding="utf-8")
    (package_root / "agent.py").write_text("VALUE = 1\n", encoding="utf-8")
    (cache_root / "agent.cpython-311.pyc").write_bytes(b"cached")

    set_deploy_env()
    deploy = importlib.import_module("tailmate.entrypoints.deploy")
    monkeypatch.setattr(deploy, "PROJECT_ROOT", source_root)
    monkeypatch.setattr(deploy, "SOURCE_BUNDLE_ROOT", tmp_path / ".agent_engine_build")

    bundle_root, extra_packages = deploy.prepare_object_bundle(bundle_name="object")

    assert extra_packages == ["tailmate"]
    assert (bundle_root / "tailmate" / "__init__.py").exists()
    assert (bundle_root / "tailmate" / "agent.py").exists()
    assert not (bundle_root / "tailmate" / "__pycache__").exists()


def test_build_deploy_request_config_object_mode_uses_flat_extra_packages(
    set_deploy_env,
    monkeypatch,
) -> None:
    set_deploy_env(
        TAILMATE_AGENT_ENGINE_STAGING_BUCKET="gs://tailmate-staging",
        TAILMATE_AGENT_ENGINE_DEPLOYMENT_MODE="object",
    )
    deploy = importlib.import_module("tailmate.entrypoints.deploy")
    monkeypatch.setattr(deploy, "validate_local_deployment_runtime", lambda: None)

    request_config = deploy.build_deploy_request_config(
        agent=deploy.app,
        config=deploy.app.config,
        display_name="tailmate-test-object",
        description="test",
        entrypoint_module=None,
        entrypoint_object=None,
        source_packages=None,
        requirements_file="deployment/agent_engine/requirements.txt",
        extra_packages=["tailmate"],
    ).model_dump(by_alias=False, exclude_none=True)

    assert request_config["staging_bucket"] == "gs://tailmate-staging"
    assert request_config["extra_packages"] == ["tailmate"]
