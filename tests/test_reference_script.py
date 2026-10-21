"""shared/scripts/reference.sh: the shared references the skills load, printed by name."""

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "shared" / "scripts" / "reference.sh"
REFERENCES = SCRIPT.parent.parent / "references"


def run(*names: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["sh", str(SCRIPT), *names], capture_output=True, text=True, cwd=cwd)


def test_it_prints_each_reference_named_from_any_folder(tmp_path):
    result = run("asking", "approving", cwd=tmp_path)
    assert result.returncode == 0
    expected = (REFERENCES / "asking.md").read_text() + (REFERENCES / "approving.md").read_text()
    assert result.stdout == expected


def test_a_reference_that_does_not_exist_fails(tmp_path):
    result = run("nope", cwd=tmp_path)
    assert result.returncode == 1
    assert result.stderr == "No reference nope.\n"


def test_it_reads_nothing_outside_its_references(tmp_path):
    for name in ("../scripts/reference", "/etc/passwd", ".hidden"):
        result = run(name, cwd=tmp_path)
        assert result.returncode == 1
        assert result.stdout == ""
