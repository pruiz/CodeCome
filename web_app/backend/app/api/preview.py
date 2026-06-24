from pathlib import Path

from fastapi import APIRouter

from app import schemas
from app.config import settings

router = APIRouter()


def preview_config_path() -> Path:
    data_dir = Path(settings.CODECOME_ROOT) / "web_app" / "backend" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "preview-analysis.md"


@router.get("/config", response_model=schemas.PreviewAnalysisConfig)
def get_preview_config():
    path = preview_config_path()
    if not path.exists():
        return schemas.PreviewAnalysisConfig(
            prompt="",
            updated=False,
        )
    return schemas.PreviewAnalysisConfig(prompt=path.read_text(), updated=True)


@router.put("/config", response_model=schemas.PreviewAnalysisConfig)
def update_preview_config(config: schemas.PreviewAnalysisConfig):
    path = preview_config_path()
    path.write_text(config.prompt)
    return schemas.PreviewAnalysisConfig(prompt=config.prompt, updated=True)
