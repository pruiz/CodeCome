from pathlib import Path


def test_worker_bootstrap_installs_and_reports_semgrep():
    root = Path(__file__).resolve().parents[2]
    script = (root / "scripts" / "worker-bootstrap.sh").read_text(encoding="utf-8")

    assert 'INSTALL_SEMGREP="${INSTALL_SEMGREP:-1}"' in script
    assert "install_semgrep()" in script
    assert "python3 -m pip install --upgrade semgrep" in script
    assert "check_command semgrep_cli 'Semgrep CLI' false semgrep --version" in script
    assert "install_semgrep" in script
