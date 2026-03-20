from pathlib import Path
import re
import subprocess
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def _read(rel_path: str) -> str:
    return (ROOT / rel_path).read_text(encoding="utf-8")


def test_release_tag_workflow_publishes_public_history_without_hosted_deploy():
    workflow = _read(".github/workflows/release-tag.yml")

    assert "uses: ./.github/workflows/mirror-public.yml" in workflow
    assert "uses: ./.github/workflows/deploy-hosted.yml" not in workflow
    assert re.search(r"publish-public:\n(?:.*\n)*?\s+contents:\s+read", workflow)
    assert "source_event_name: push" in workflow
    assert "source_ref_type: tag" in workflow
    assert "source_ref_name: ${{ github.ref_name }}" in workflow
    assert "source_sha: ${{ github.sha }}" in workflow


def test_mirror_public_workflow_is_reusable_and_still_manual_dispatchable():
    workflow = _read(".github/workflows/mirror-public.yml")

    assert "workflow_call:" in workflow
    assert "workflow_dispatch:" in workflow
    assert "source_sha:" in workflow
    assert "source_ref_name:" in workflow
    assert "Manual public release must be dispatched from master" in workflow
    assert "must point to a commit already merged into master" in workflow
    assert "Build public GitHub Release notes" in workflow
    assert "Create or update public GitHub Release" in workflow
    assert "gh release create" in workflow
    assert "gh release edit" in workflow
    assert "--latest" in workflow
    assert "public-release-applied-commits.md" in workflow
    assert "公开仓差异对比" in workflow


def test_internal_release_pipeline_files_stay_out_of_public_snapshot():
    excluded = _read(".github/public-mirror-exclude.txt")

    assert ".github/workflows/deploy-hosted.yml" in excluded
    assert ".github/workflows/release-tag.yml" in excluded
    assert ".github/workflows/mirror-public.yml" in excluded
    assert ".github/workflows/docker-publish.yml" in excluded
    assert "scripts/deploy_hosted.sh" in excluded


def test_hosted_deploy_script_keeps_healthcheck_and_metadata_contract():
    script = _read("scripts/deploy_hosted.sh")
    uv_version = _read(".uv-version").strip()

    assert "http://localhost:8000/api/health" in script
    assert "NOVWR_HEALTHCHECK_RETRIES" in script
    assert "last-success.env" in script
    assert "current-sha.txt" in script
    assert "systemctl restart novwr" in script
    assert 'UV_VERSION_FILE="${NOVWR_UV_VERSION_FILE:-$ROOT_DIR/.uv-version}"' in script
    assert f'https://astral.sh/uv/{uv_version}/install.sh' not in script
    assert 'https://astral.sh/uv/${uv_version}/install.sh' in script
    assert "scripts/setup_python_env.sh" in script
    assert "--no-dev" in script
    assert "astral.sh/uv/install.sh" not in script
    assert "requirements.txt" not in script
    assert "resolve_uv_version" in script


def test_python_environment_bootstrap_is_uv_lock_driven():
    setup_script = _read("scripts/setup_python_env.sh")
    pyproject = _read("pyproject.toml")
    pyproject_data = tomllib.loads(pyproject)
    uv_version = _read(".uv-version").strip()

    assert "uv venv" in setup_script
    assert "uv sync" in setup_script
    assert "--frozen" in setup_script
    assert "--no-install-project" in setup_script
    assert "[project]" in pyproject
    assert "[dependency-groups]" in pyproject
    assert 'requires-python = ">=3.13,<3.14"' in pyproject
    assert pyproject_data["project"]["scripts"]["novwr"] == "app.cli:main"
    assert pyproject_data["tool"]["uv"]["package"] is True
    assert pyproject_data["tool"]["uv"]["required-version"] == f"=={uv_version}"


def test_uv_version_generated_targets_are_in_sync():
    completed = subprocess.run(
        [sys.executable, "scripts/sync_uv_version.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_dockerfile_allows_frontend_build_mode_overrides():
    dockerfile = _read("Dockerfile")

    assert "# syntax=docker/dockerfile:1.7" in dockerfile
    assert "ARG VITE_DEPLOY_MODE=selfhost" in dockerfile
    assert 'VITE_DEPLOY_MODE="$VITE_DEPLOY_MODE"' in dockerfile
    assert "COPY .uv-version ./" in dockerfile
    assert 'env UV_UNMANAGED_INSTALL="/uv-bin" sh' in dockerfile
    assert "--mount=type=cache,target=/root/.cache/uv" in dockerfile
    assert "COPY data/demo/ data/demo/" in dockerfile
    assert "COPY data/worldpacks/ data/worldpacks/" in dockerfile
    assert "python:3.13-slim" in dockerfile
    assert "scripts/setup_python_env.sh --no-dev" in dockerfile
    assert "COPY --from=backend-build /app/.venv /app/.venv" in dockerfile
    assert "COPY --from=uv /uv /uvx /bin/" not in dockerfile
    assert "USER app" not in dockerfile


def test_docker_build_context_keeps_demo_seed_assets():
    dockerignore = _read(".dockerignore")

    assert "!data/demo/" in dockerignore
    assert "!data/demo/**" in dockerignore
    assert "!data/worldpacks/" in dockerignore
    assert "!data/worldpacks/**" in dockerignore


def test_hosted_compose_builds_frontend_in_hosted_mode():
    compose = _read("deploy/hosted/docker-compose.yml")

    assert "VITE_DEPLOY_MODE: hosted" in compose


def test_selfhost_compose_template_uses_official_image():
    compose = _read("deploy/selfhost/docker-compose.yml")

    assert "ghcr.io/hurricane0698/novelwriter:latest" in compose
    assert "${NOVWR_BIND_HOST:-127.0.0.1}:${NOVWR_PORT:-8000}:8000" in compose
    assert "${NOVWR_DATA_DIR:-./data}:/data" in compose


def test_ci_workflow_uses_uv_for_backend_jobs():
    workflow = _read(".github/workflows/ci.yml")

    assert "astral-sh/setup-uv@v7" in workflow
    assert "version-file: pyproject.toml" in workflow
    assert "./scripts/setup_python_env.sh" in workflow
    assert "./scripts/uv_run.sh pytest tests/" in workflow
    assert "pip install -r requirements.txt" not in workflow
    assert "uses: ./.github/workflows/ci-selfhost-smoke.yml" in workflow


def test_selfhost_smoke_workflow_gates_pr_installer_and_compose_paths():
    workflow = _read(".github/workflows/ci-selfhost-smoke.yml")

    assert "workflow_call:" in workflow
    assert "Selfhost install smoke" in workflow
    assert "astral-sh/setup-uv@v7" in workflow
    assert "version-file: pyproject.toml" in workflow
    assert "./scripts/selfhost_smoke.sh" in workflow


def test_selfhost_smoke_script_covers_wheel_installer_and_compose_flows():
    script = _read("scripts/selfhost_smoke.sh")

    assert 'docker build -t "$SMOKE_IMAGE_TAG" .' in script
    assert 'uv build --wheel --out-dir dist' in script
    assert 'uv tool run --isolated --from "$WHEEL_PATH" novwr --help' in script
    assert 'uv tool run --isolated --from "$WHEEL_PATH" novwr uninstall --help' in script
    assert 'curl -fsSL "file://${ROOT_DIR}/install.sh" | bash' in script
    assert 'export NOVWR_UV_VERSION="$(tr -d ' in script
    assert '"$NOVWR_BIN" doctor --dir "$INSTALL_DIR"' in script
    assert "unset NOVWR_HOME NOVWR_IMAGE NOVWR_BIND_HOST NOVWR_PORT NOVWR_PACKAGE_SPEC NOVWR_UV_VERSION" in script
    assert 'cp deploy/selfhost/docker-compose.yml "$COMPOSE_DIR/docker-compose.yml"' in script
    assert 'docker compose --project-directory "$COMPOSE_DIR" --project-name "$COMPOSE_PROJECT_NAME" up -d' in script
    assert 'dump_compose_debug()' in script
    assert 'docker compose "${compose_args[@]}" logs --no-color || true' in script


def test_playwright_integration_backend_server_uses_uv_wrapper():
    config = _read("web/playwright.config.ts")

    assert "./scripts/uv_run.sh uvicorn app.main:app --port 8000" in config


def test_install_script_bootstraps_novwr_cli_and_runs_init_then_run():
    script = _read("install.sh")

    assert 'NOVWR_UV_VERSION="${NOVWR_UV_VERSION:-}"' in script
    assert "DEFAULT_NOVWR_UV_VERSION" in script
    assert 'curl -LsSf "https://astral.sh/uv/${uv_version}/install.sh" -o "$installer"' in script
    assert "raw.githubusercontent.com" in script
    assert ".uv-version" in script
    assert "NOVWR_PACKAGE_SPEC" in script
    assert "archive/refs/heads/master.tar.gz" in script
    assert 'if [[ "$package_spec" == git+* ]]; then' in script
    assert "ensure_command git" in script
    assert 'uv tool install --force "$package_spec"' in script
    assert 'init_args=(init --dir "$NOVWR_HOME")' in script
    assert 'novwr run --dir "$NOVWR_HOME"' in script
    assert 'novwr doctor --dir "$NOVWR_HOME"' in script
    assert 'novwr uninstall --dir "$NOVWR_HOME"' in script


def test_docker_publish_workflow_gates_latest_on_master_ci_success():
    workflow = _read(".github/workflows/docker-publish.yml")

    assert "workflow_run:" in workflow
    assert re.search(r"workflows:\n\s+- CI", workflow)
    assert re.search(r"types:\n\s+- completed", workflow)
    assert re.search(r"branches:\n\s+- master", workflow)
    assert "github.event.workflow_run.conclusion == 'success'" in workflow
    assert "github.event.workflow_run.head_sha" in workflow
    assert "docker/login-action@v3" in workflow
    assert "docker/metadata-action@v5" in workflow
    assert "docker/build-push-action@v6" in workflow
    assert "ghcr.io/${{ github.repository_owner }}/novelwriter" in workflow
    assert "type=raw,value=latest" in workflow
    assert "type=ref,event=tag" in workflow
    assert "type=raw,value=latest,enable={{is_default_branch}}" not in workflow


def test_hosted_deploy_workflow_bootstraps_script_from_origin_master_for_rollbacks():
    workflow = _read(".github/workflows/deploy-hosted.yml")

    assert "git show origin/master:scripts/deploy_hosted.sh" in workflow
    assert "bash .deploy/deploy_hosted.sh" in workflow
    assert (
        "git fetch origin refs/heads/master:refs/remotes/origin/master --tags --force"
        in workflow
    )
    assert "git checkout --detach %q && NOVWR_PREVIOUS_SHA" not in workflow
