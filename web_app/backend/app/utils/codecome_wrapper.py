import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Optional, List, Dict, Any
from dataclasses import dataclass, field
import yaml
from datetime import datetime
from app.config import settings


@dataclass
class ExecutionResult:
    exit_code: int
    stdout: str
    stderr: str
    duration: float
    started_at: datetime
    completed_at: datetime
    metadata: dict = field(default_factory=dict)


class CodeComeExecutor:
    """Wraps existing CodeCome make commands for phase execution."""
    
    def __init__(self):
        self.codecome_root = settings.CODECOME_ROOT
    
    def execute_phase(
        self,
        workspace_path: Path,
        phase: str,  # "phase-1", "phase-2", etc.
        model: Optional[str] = None,
        variant: Optional[str] = None,
        finding_id: Optional[str] = None,
        env_overrides: Optional[dict] = None,
        thinking: bool = False,
        output_callback: Optional[Callable[[str, str], None]] = None,
        process_callback: Optional[Callable[[int, list[str]], None]] = None,
    ) -> ExecutionResult:
        """
        Execute a CodeCome phase using make command.
        
        Steps:
        1. Change to workspace directory
        2. Set environment variables (CODECOME_MODEL, etc.)
        3. Run: make {phase} [FINDING={finding_id}]
        4. Return: exit_code, stdout, stderr, duration
        """
        env = os.environ.copy()
        
        # Preserve the virtualenv path from CodeCome root
        venv_python = self.codecome_root / ".venv" / "bin" / "python3"
        if venv_python.exists():
            env["VIRTUAL_ENV"] = str(self.codecome_root / ".venv")
            venv_bin = str(self.codecome_root / ".venv" / "bin")
            env["PATH"] = f"{venv_bin}:{env.get('PATH', '')}"
        
        if model:
            env["CODECOME_MODEL"] = model
        if variant:
            env["CODECOME_MODEL_VARIANT"] = variant
        if thinking:
            env["CODECOME_THINKING"] = "1"
        
        if env_overrides:
            env.update(env_overrides)
        
        # Build command
        commands = []
        if not (workspace_path / ".venv" / "bin" / "python3").exists():
            commands.append(["make", "init"])

        cmd = ["make", phase]
        if finding_id:
            cmd.append(f"FINDING={finding_id}")
        commands.append(cmd)
        
        started_at = datetime.now()
        
        # Run command
        try:
            stdout_parts = []
            stderr_parts = []
            exit_code = 0

            for current_cmd in commands:
                if output_callback:
                    output_callback("system", f"$ {' '.join(current_cmd)}")

                process = subprocess.Popen(
                    current_cmd,
                    cwd=str(workspace_path),
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    preexec_fn=os.setsid,
                )
                if process_callback:
                    process_callback(process.pid, current_cmd)

                def read_stream(stream, parts, source):
                    for line in iter(stream.readline, ""):
                        parts.append(line)
                        if output_callback and line.strip():
                            output_callback(source, line.rstrip("\n"))
                    stream.close()

                stdout_thread = threading.Thread(target=read_stream, args=(process.stdout, stdout_parts, "stdout"))
                stderr_thread = threading.Thread(target=read_stream, args=(process.stderr, stderr_parts, "stderr"))
                stdout_thread.start()
                stderr_thread.start()

                try:
                    process.wait(timeout=7200)
                except subprocess.TimeoutExpired:
                    self.terminate_process_group(process.pid)
                    exit_code = -1
                stdout_thread.join(timeout=5)
                stderr_thread.join(timeout=5)
                exit_code = process.returncode if exit_code != -1 else -1

                if exit_code != 0:
                    break

            stdout = "".join(stdout_parts)
            stderr = "".join(stderr_parts)
            
        except subprocess.TimeoutExpired:
            exit_code = -1
            stdout = ""
            stderr = "Command timed out"
        except Exception as e:
            return ExecutionResult(
                exit_code=-1,
                stdout="",
                stderr=str(e),
                duration=0,
                started_at=started_at,
                completed_at=datetime.now()
            )
        
        completed_at = datetime.now()
        duration = (completed_at - started_at).total_seconds()
        
        return ExecutionResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration=duration,
            started_at=started_at,
            completed_at=completed_at
        )

    def execute_make_target(
        self,
        workspace_path: Path,
        target: str,
        output_callback: Optional[Callable[[str, str], None]] = None,
        process_callback: Optional[Callable[[int, list[str]], None]] = None,
        env_overrides: Optional[dict] = None,
        timeout: int = 7200,
    ) -> ExecutionResult:
        started_at = datetime.now()
        stdout_parts = []
        stderr_parts = []
        exit_code = 0
        env = os.environ.copy()
        if env_overrides:
            env.update({str(k): str(v) for k, v in env_overrides.items()})

        try:
            cmd = ["make", target]
            if output_callback:
                output_callback("system", f"$ {' '.join(cmd)}")
            process = subprocess.Popen(
                cmd,
                cwd=str(workspace_path),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                preexec_fn=os.setsid,
            )
            if process_callback:
                process_callback(process.pid, cmd)

            def read_stream(stream, parts, source):
                for line in iter(stream.readline, ""):
                    parts.append(line)
                    if output_callback and line.strip():
                        output_callback(source, line.rstrip("\n"))
                stream.close()

            stdout_thread = threading.Thread(target=read_stream, args=(process.stdout, stdout_parts, "stdout"))
            stderr_thread = threading.Thread(target=read_stream, args=(process.stderr, stderr_parts, "stderr"))
            stdout_thread.start()
            stderr_thread.start()

            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.terminate_process_group(process.pid)
                exit_code = -1
            stdout_thread.join(timeout=5)
            stderr_thread.join(timeout=5)
            exit_code = process.returncode if exit_code != -1 else -1
        except Exception as exc:
            exit_code = -1
            stderr_parts.append(str(exc))

        completed_at = datetime.now()
        return ExecutionResult(
            exit_code=exit_code,
            stdout="".join(stdout_parts),
            stderr="".join(stderr_parts),
            duration=(completed_at - started_at).total_seconds(),
            started_at=started_at,
            completed_at=completed_at,
        )

    @staticmethod
    def terminate_process_group(pid: int) -> None:
        pgid = None
        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            return
        except Exception:
            try:
                os.kill(pid, signal.SIGTERM)
            except Exception:
                return

        time.sleep(2)
        try:
            if pgid is not None:
                os.killpg(pgid, 0)
                os.killpg(pgid, signal.SIGKILL)
            else:
                os.kill(pid, 0)
                os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        except Exception:
            return
    
    def parse_findings(self, workspace_path: Path) -> List[Dict[str, Any]]:
        """
        Parse findings from itemdb/findings/*/*.md
        
        Returns list of dicts with:
        - id, title, status, severity, confidence
        - frontmatter (parsed YAML)
        - content (full markdown)
        """
        findings = []
        findings_dir = workspace_path / "itemdb" / "findings"
        
        if not findings_dir.exists():
            return findings
        
        status_dirs = ["PENDING", "CONFIRMED", "EXPLOITED", "REJECTED", "DUPLICATE"]
        
        for status in status_dirs:
            status_path = findings_dir / status
            if not status_path.exists():
                continue
            
            for finding_file in status_path.glob("*.md"):
                if finding_file.name.startswith("."):
                    continue
                
                finding_data = self._parse_finding_file(finding_file, status)
                if finding_data:
                    findings.append(finding_data)
        
        return findings
    
    def _parse_finding_file(self, file_path: Path, status: str) -> Optional[Dict[str, Any]]:
        """Parse YAML frontmatter + markdown content from finding file."""
        try:
            content = file_path.read_text()
        except Exception:
            return None
        
        # Parse YAML frontmatter
        frontmatter = {}
        markdown_content = content
        
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                try:
                    frontmatter = yaml.safe_load(parts[1]) or {}
                    markdown_content = parts[2]
                except yaml.YAMLError:
                    frontmatter = {}
                    markdown_content = content
        
        # Extract key fields
        finding_id = frontmatter.get("id", file_path.stem)
        title = frontmatter.get("title", finding_id)
        severity = frontmatter.get("severity", "INFO")
        confidence = frontmatter.get("confidence", "LOW")
        category = frontmatter.get("category", "Unknown")
        
        # Get file path from frontmatter
        file_path_value = None
        files = frontmatter.get("files", [])
        if files and isinstance(files, list) and len(files) > 0:
            file_path_value = files[0]
        
        # Check for evidence
        evidence_dir = None
        has_evidence = False
        has_exploit = False
        
        if "validation" in frontmatter:
            validation = frontmatter["validation"]
            if isinstance(validation, dict):
                evidence_dir = validation.get("evidence_dir")
        
        # Check evidence directory
        evidence_path = file_path.parent.parent.parent / "evidence" / finding_id
        if evidence_path.exists():
            has_evidence = True
            evidence_dir = f"itemdb/evidence/{finding_id}"
        
        # Check for exploit
        exploit_path = evidence_path / "exploits" if evidence_path.exists() else None
        if exploit_path and exploit_path.exists():
            has_exploit = True
        
        return {
            "id": finding_id,
            "title": title,
            "status": status,
            "severity": severity,
            "confidence": confidence,
            "category": category,
            "file_path": file_path_value,
            "frontmatter": frontmatter,
            "content": markdown_content.strip(),
            "content_preview": markdown_content.strip()[:500] if markdown_content else "",
            "evidence_dir": evidence_dir,
            "has_evidence": has_evidence,
            "has_exploit": has_exploit
        }
    
    def get_phase_artifacts(self, workspace_path: Path, phase: str) -> Dict[str, Any]:
        """Get artifacts produced by a phase execution."""
        artifacts = {}
        
        # Check for run summary
        runs_dir = workspace_path / "runs"
        if runs_dir.exists():
            for summary_file in runs_dir.glob(f"phase-{phase.split('-')[-1]}-summary-*.md"):
                artifacts["run_summary_path"] = str(summary_file)
                break
        
        # Check for generated notes (Phase 1)
        if phase == "phase-1":
            notes_path = workspace_path / "itemdb" / "notes"
            if notes_path.exists():
                artifacts["notes"] = [f.name for f in notes_path.glob("*.md")]
        
        # Check for findings
        findings = self.parse_findings(workspace_path)
        artifacts["findings_count"] = len(findings)
        
        return artifacts


codecome_executor = CodeComeExecutor()
