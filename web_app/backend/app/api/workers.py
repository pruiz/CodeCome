from pathlib import Path
import json
import shutil
import subprocess

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app import crud, schemas
from app.config import settings
from app.database import get_db

router = APIRouter()


def worker_opencode_config_path() -> Path:
    data_dir = Path(settings.CODECOME_ROOT) / "web_app" / "backend" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "worker-opencode.jsonc"


def command_version(command: str, args: list[str] | None = None) -> tuple[bool, str]:
    if not shutil.which(command):
        return False, "not found"
    try:
        result = subprocess.run([command, *(args or ["--version"])], capture_output=True, text=True, timeout=10)
        output = (result.stdout or result.stderr or "installed").strip().splitlines()[0]
        return result.returncode == 0, output
    except Exception as exc:
        return False, str(exc)


def executable_version(path: Path, args: list[str] | None = None) -> tuple[bool, str]:
    if not path.exists() or not path.is_file():
        return False, "not found"
    try:
        result = subprocess.run([str(path), *(args or ["--version"])], capture_output=True, text=True, timeout=10)
        output = (result.stdout or result.stderr or "installed").strip().splitlines()[0]
        return result.returncode == 0, f"{output} ({path})"
    except Exception as exc:
        return False, str(exc)


def codeql_version() -> tuple[bool, str]:
    path_ok, path_detail = command_version("codeql", ["--version"])
    if path_ok:
        return True, f"{path_detail} (PATH)"

    root = Path(settings.CODECOME_ROOT)
    candidates = [
        root / ".tools" / "codeql" / "linux64" / "current" / "codeql",
        root / ".tools" / "codeql" / "osx64" / "current" / "codeql",
        root / ".tools" / "codeql" / "win64" / "current" / "codeql.exe",
    ]
    for candidate in candidates:
        ok, detail = executable_version(candidate, ["--version"])
        if ok:
            return True, detail

    return False, "not found in PATH or CodeCome managed .tools/codeql/*/current"


def local_requirement_checks() -> list[schemas.WorkerRequirementCheck]:
    checks: list[schemas.WorkerRequirementCheck] = []

    opencode_ok, opencode_detail = command_version("opencode", ["--version"])
    checks.append(schemas.WorkerRequirementCheck(
        key="opencode_installed",
        label="OpenCode installed",
        required=True,
        ok=opencode_ok,
        detail=opencode_detail,
    ))

    config_paths = [
        Path.home() / ".config" / "opencode" / "opencode.jsonc",
        Path.home() / ".config" / "opencode" / "opencode.json",
    ]
    existing_config = next((path for path in config_paths if path.exists()), None)
    checks.append(schemas.WorkerRequirementCheck(
        key="opencode_configured",
        label="OpenCode provider configured",
        required=True,
        ok=existing_config is not None,
        detail=str(existing_config) if existing_config else "No ~/.config/opencode/opencode.jsonc or opencode.json found",
    ))

    python_ok = False
    python_detail = "not found"
    if shutil.which("python3"):
        result = subprocess.run(["python3", "-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))"], capture_output=True, text=True, timeout=10)
        python_detail = result.stdout.strip() or result.stderr.strip()
        parts = python_detail.split(".")[:2]
        python_ok = result.returncode == 0 and len(parts) == 2 and tuple(map(int, parts)) >= (3, 10)
    checks.append(schemas.WorkerRequirementCheck(
        key="python_310",
        label="Python 3.10+",
        required=True,
        ok=python_ok,
        detail=python_detail,
    ))

    make_ok, make_detail = command_version("make", ["--version"])
    checks.append(schemas.WorkerRequirementCheck(
        key="gnu_make",
        label="GNU Make",
        required=True,
        ok=make_ok,
        detail=make_detail,
    ))

    docker_cmd_ok, docker_detail = command_version("docker", ["--version"])
    docker_daemon_ok = False
    if docker_cmd_ok:
        daemon = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=10)
        docker_daemon_ok = daemon.returncode == 0
        if not docker_daemon_ok:
            docker_detail = (daemon.stderr or daemon.stdout or docker_detail).strip().splitlines()[0]
    checks.append(schemas.WorkerRequirementCheck(
        key="docker",
        label="Docker CLI and daemon",
        required=True,
        ok=docker_cmd_ok and docker_daemon_ok,
        detail=docker_detail,
    ))

    codeql_ok, codeql_detail = codeql_version()
    checks.append(schemas.WorkerRequirementCheck(
        key="codeql_cli",
        label="CodeQL CLI",
        required=False,
        ok=codeql_ok,
        detail=codeql_detail,
    ))

    for key, label, cmd in [
        ("asciinema", "asciinema", "asciinema"),
        ("agg", "agg", "agg"),
        ("xvfb", "Xvfb / xvfb-run", "Xvfb"),
    ]:
        ok, detail = command_version(cmd, ["--version"])
        if key == "xvfb" and not ok:
            ok, detail = command_version("xvfb-run", ["--help"])
        checks.append(schemas.WorkerRequirementCheck(
            key=key,
            label=label,
            required=False,
            ok=ok,
            detail=detail,
        ))

    ffmpeg_ok, ffmpeg_detail = command_version("ffmpeg", ["-version"])
    checks.append(schemas.WorkerRequirementCheck(
        key="ffmpeg",
        label="ffmpeg",
        required=False,
        ok=ffmpeg_ok,
        detail=ffmpeg_detail,
    ))

    return checks


def checks_from_worker_config(worker) -> list[schemas.WorkerRequirementCheck]:
    config = worker.config or {}
    raw_checks = config.get("requirements") or config.get("checks") or []
    checks = []
    for item in raw_checks:
        if isinstance(item, dict):
            checks.append(schemas.WorkerRequirementCheck(
                key=str(item.get("key", "unknown")),
                label=str(item.get("label", item.get("key", "Unknown"))),
                required=bool(item.get("required", True)),
                ok=bool(item.get("ok", False)),
                detail=str(item.get("detail", "")),
            ))
    return checks


def redacted_config(config: dict | None) -> dict:
    safe = dict(config or {})
    auth = safe.get("ssh_auth")
    if isinstance(auth, dict):
        safe["ssh_auth"] = {
            "method": auth.get("method", "key"),
            "has_password": bool(auth.get("password")),
            "has_private_key": bool(auth.get("private_key")),
            "has_passphrase": bool(auth.get("passphrase")),
        }
    return safe


def worker_response(worker) -> dict:
    return {
        "id": worker.id,
        "name": worker.name,
        "type": worker.type,
        "status": worker.status,
        "host": worker.host,
        "port": worker.port,
        "username": worker.username,
        "workspace_base_path": worker.workspace_base_path,
        "max_concurrent_jobs": worker.max_concurrent_jobs,
        "current_jobs": worker.current_jobs,
        "capabilities": worker.capabilities or {},
        "config": redacted_config(worker.config),
        "last_seen": worker.last_seen,
        "created_at": worker.created_at,
        "updated_at": worker.updated_at,
    }


@router.get("/bootstrap-script", response_class=PlainTextResponse)
def get_worker_bootstrap_script():
    """Return the standalone bootstrap script for VM/LXC/physical workers."""
    script_path = Path(settings.CODECOME_ROOT) / "web_app" / "scripts" / "worker-bootstrap.sh"
    if not script_path.exists():
        raise HTTPException(status_code=404, detail="Bootstrap script not found")
    return PlainTextResponse(script_path.read_text(), media_type="text/x-shellscript")


@router.get("/opencode-config", response_model=schemas.WorkerOpenCodeConfig)
def get_worker_opencode_config():
    """Return the OpenCode config that bootstrap workers can pull."""
    config_path = worker_opencode_config_path()
    if not config_path.exists():
        return schemas.WorkerOpenCodeConfig(content="", updated=False)
    return schemas.WorkerOpenCodeConfig(content=config_path.read_text(), updated=True)


@router.put("/opencode-config", response_model=schemas.WorkerOpenCodeConfig)
def update_worker_opencode_config(config: schemas.WorkerOpenCodeConfig):
    """Store the OpenCode config used by remote worker bootstrap."""
    config_path = worker_opencode_config_path()
    config_path.write_text(config.content)
    return schemas.WorkerOpenCodeConfig(content=config.content, updated=True)


@router.get("/opencode-config/raw", response_class=PlainTextResponse)
def get_worker_opencode_config_raw():
    """Return raw OpenCode config for OPENCODE_CONFIG_URL in worker bootstrap."""
    config_path = worker_opencode_config_path()
    if not config_path.exists():
        raise HTTPException(status_code=404, detail="Worker OpenCode config not configured")
    return PlainTextResponse(config_path.read_text(), media_type="application/json")


@router.post("/", response_model=schemas.WorkerResponse, status_code=201)
def create_worker(worker_data: schemas.WorkerCreate, db: Session = Depends(get_db)):
    """Register a worker that can execute CodeCome audits."""
    if crud.get_worker_by_name(db, worker_data.name):
        raise HTTPException(status_code=409, detail="Worker name already exists")
    return worker_response(crud.create_worker(db, worker_data))


@router.get("/", response_model=schemas.WorkerListResponse)
def list_workers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    status: str | None = Query(None),
    include_default: bool = Query(True),
    db: Session = Depends(get_db),
):
    """List registered workers."""
    if include_default:
        crud.ensure_local_worker(db)
    total, workers = crud.get_workers(db, skip, limit, status)
    return schemas.WorkerListResponse(total=total, workers=[worker_response(worker) for worker in workers])


@router.get("/{worker_id}", response_model=schemas.WorkerResponse)
def get_worker(worker_id: int, db: Session = Depends(get_db)):
    """Get one worker."""
    worker = crud.get_worker(db, worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    return worker_response(worker)


@router.get("/{worker_id}/checks", response_model=schemas.WorkerChecksResponse)
def get_worker_checks(worker_id: int, db: Session = Depends(get_db)):
    """Return CodeCome prerequisite checks for a worker."""
    worker = crud.get_worker(db, worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    if worker.type == "local":
        return schemas.WorkerChecksResponse(
            worker_id=worker.id,
            worker_name=worker.name,
            source="live-local",
            checks=local_requirement_checks(),
        )

    checks = checks_from_worker_config(worker)
    return schemas.WorkerChecksResponse(
        worker_id=worker.id,
        worker_name=worker.name,
        source="bootstrap-metadata" if checks else "unreported",
        checks=checks,
    )


@router.patch("/{worker_id}", response_model=schemas.WorkerResponse)
def update_worker(worker_id: int, worker_data: schemas.WorkerUpdate, db: Session = Depends(get_db)):
    """Update worker metadata or status."""
    worker = crud.update_worker(db, worker_id, worker_data)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    return worker_response(worker)


@router.delete("/{worker_id}", status_code=204)
def delete_worker(worker_id: int, db: Session = Depends(get_db)):
    """Remove a worker registration."""
    worker = crud.get_worker(db, worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    if worker.current_jobs:
        raise HTTPException(status_code=409, detail="Worker has active jobs")
    crud.delete_worker(db, worker_id)


@router.post("/{worker_id}/heartbeat", response_model=schemas.WorkerResponse)
def worker_heartbeat(worker_id: int, db: Session = Depends(get_db)):
    """Mark a worker as alive."""
    worker = crud.get_worker(db, worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    update = schemas.WorkerUpdate(status="idle" if worker.current_jobs == 0 else "running")
    return worker_response(crud.update_worker(db, worker_id, update))
