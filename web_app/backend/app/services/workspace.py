from pathlib import Path
from typing import Optional
from app.config import settings
import shutil
import zipfile
import tarfile


class WorkspaceManager:
    def __init__(self):
        self.base_dir = settings.WORKSPACES_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.codecome_root = settings.CODECOME_ROOT
    
    def create_workspace(self, audit_id: str) -> Path:
        """Create isolated workspace directory for an audit."""
        workspace_name = f"audit-{audit_id}"
        workspace_path = self.base_dir / workspace_name
        
        # Create directory structure
        for subdir in ["src", "itemdb/notes", "itemdb/findings/PENDING", "itemdb/findings/CONFIRMED",
                       "itemdb/findings/EXPLOITED", "itemdb/findings/REJECTED", "itemdb/findings/DUPLICATE",
                       "itemdb/evidence", "itemdb/reports", "sandbox", "runs", "tmp"]:
            (workspace_path / subdir).mkdir(parents=True, exist_ok=True)
        
        # Write .gitkeep files
        for keep in ["itemdb/notes/.gitkeep", "itemdb/findings/PENDING/.gitkeep",
                     "itemdb/findings/CONFIRMED/.gitkeep", "itemdb/findings/EXPLOITED/.gitkeep",
                     "itemdb/findings/REJECTED/.gitkeep", "itemdb/findings/DUPLICATE/.gitkeep",
                     "itemdb/evidence/.gitkeep", "itemdb/reports/.gitkeep", "runs/.gitkeep", "tmp/.gitkeep"]:
            keep_path = workspace_path / keep
            keep_path.touch()
        
        # Copy CodeCome CLI tool files
        self._copy_cli_files(workspace_path)
        
        return workspace_path
    
    def _copy_cli_files(self, workspace_path: Path) -> None:
        """Copy CodeCome CLI tool files to workspace."""
        import shutil
        
        cli_files = [
            ("Makefile", "Makefile"),
            ("codecome.yml", "codecome.yml"),
            ("AGENTS.md", "AGENTS.md"),
            ("README.md", "README.md"),
            ("requirements.txt", "requirements.txt"),
            ("prompts", "prompts"),
            ("templates", "templates"),
            ("tools", "tools"),
            (".opencode", ".opencode"),
            (".github", ".github")
        ]
        
        for src_name, dst_name in cli_files:
            src = self.codecome_root / src_name
            dst = workspace_path / dst_name
            if src.exists():
                if src.is_dir():
                    if dst.exists():
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst, symlinks=True)
                else:
                    shutil.copy2(src, dst)
    
    def setup_source_from_git(self, workspace_path: Path, git_url: str) -> bool:
        """Clone git repository to workspace/src/."""
        import subprocess
        
        src_path = workspace_path / "src"
        src_path.mkdir(exist_ok=True)
        
        try:
            result = subprocess.run(
                ["git", "clone", git_url, "."],
                cwd=src_path,
                capture_output=True,
                text=True,
                timeout=300
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, Exception):
            return False
    
    def setup_source_from_zip(self, workspace_path: Path, zip_path: str) -> bool:
        """Extract ZIP to workspace/src/."""
        src_path = workspace_path / "src"
        src_path.mkdir(exist_ok=True)
        
        try:
            # Check if it's a ZIP or tar.gz
            if zip_path.endswith('.zip'):
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    zf.extractall(src_path)
            elif zip_path.endswith('.tar.gz') or zip_path.endswith('.tgz'):
                with tarfile.open(zip_path, 'r:gz') as tar:
                    tar.extractall(src_path, filter='data')
            else:
                return False
            
            return True
        except Exception:
            return False
    
    def setup_source_from_local(self, workspace_path: Path, local_path: str) -> bool:
        """Copy local directory to workspace/src/."""
        src_path = workspace_path / "src"
        src_path.mkdir(exist_ok=True)
        
        try:
            local = Path(local_path)
            if local.is_dir():
                for item in local.iterdir():
                    dest = src_path / item.name
                    if item.is_dir():
                        shutil.copytree(item, dest, dirs_exist_ok=True)
                    else:
                        shutil.copy2(item, dest)
            elif local.is_file():
                shutil.copy2(local, src_path)
            return True
        except Exception:
            return False
    
    def write_codecome_yml(self, workspace_path: Path, yml_content: str) -> bool:
        """Write codecome.yml to workspace root."""
        try:
            yml_path = workspace_path / "codecome.yml"
            yml_path.write_text(yml_content)
            return True
        except Exception:
            return False
    
    def get_codecome_yml(self, workspace_path: Path) -> Optional[str]:
        """Read existing codecome.yml."""
        yml_path = workspace_path / "codecome.yml"
        if yml_path.exists():
            return yml_path.read_text()
        return None
    
    def cleanup_workspace(self, workspace_path: Path) -> bool:
        """Remove workspace directory and contents."""
        try:
            if workspace_path.exists():
                shutil.rmtree(workspace_path)
            return True
        except Exception:
            return False
    
    def validate_workspace(self, workspace_path: Path) -> bool:
        """Check if workspace has required structure."""
        required = ["src", "itemdb", "codecome.yml"]
        for req in required:
            if not (workspace_path / req).exists():
                return False
        return True
    
    def get_workspace_path(self, audit_id: str) -> Path:
        """Get workspace path for an audit."""
        return self.base_dir / f"audit-{audit_id}"


workspace_manager = WorkspaceManager()
