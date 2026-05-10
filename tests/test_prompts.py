import re
from pathlib import Path

def test_prompt_safeguards():
    """Ensure prompts enforce CLI usage and frontmatter validation."""
    prompts_dir = Path("prompts")
    
    # Phase 3, 4, 5 should enforce using make findings-move
    for phase in ["phase-3-review.md", "phase-4-validate.md", "phase-5-exploit.md"]:
        content = (prompts_dir / phase).read_text(encoding="utf-8")
        assert "make findings-move" in content, f"{phase} is missing make findings-move instruction"
        
    # All modification phases should run frontmatter check
    for phase in ["phase-2-audit.md", "phase-3-review.md", "phase-4-validate.md", "phase-5-exploit.md"]:
        content = (prompts_dir / phase).read_text(encoding="utf-8")
        assert "make frontmatter" in content, f"{phase} is missing make frontmatter instruction"
