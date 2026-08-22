#!/usr/bin/env python3
"""
Skill Builder & Packager - Validates and packages a skill folder into a distributable zip file.

Usage:
    python build_skill.py <path/to/skill-folder> [output-directory]

Example:
    python build_skill.py output/xin-novel-style-santi
    python build_skill.py output/xin-novel-style-santi ./dist

The script will:
1. Validate the skill (SKILL.md exists, frontmatter format, name convention)
2. Package the skill into a zip file named after the skill folder
3. The zip preserves the skill directory as the top-level folder
"""

import sys
import os
import re
import zipfile
from pathlib import Path


def safe_print(message):
    """Print message safely, handling emoji encoding issues on Windows."""
    try:
        print(message)
    except UnicodeEncodeError:
        import re as re_module
        clean_message = re_module.sub(r'[\U0001F300-\U0001F9FF]', '', message)
        print(clean_message.strip())


# Enable UTF-8 on Windows
if sys.platform == 'win32':
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


def validate_skill(skill_path):
    """
    Validate a skill folder.

    Args:
        skill_path: Path to the skill folder

    Returns:
        Tuple (bool, str): (is_valid, message)
    """
    skill_path = Path(skill_path)

    # Check SKILL.md exists
    skill_md = skill_path / 'SKILL.md'
    if not skill_md.exists():
        return False, "SKILL.md not found"

    # Read and validate frontmatter
    content = skill_md.read_text(encoding='utf-8')
    if not content.startswith('---'):
        return False, "No YAML frontmatter found"

    # Extract frontmatter
    match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
    if not match:
        return False, "Invalid frontmatter format"

    frontmatter = match.group(1)

    # Check required fields
    if 'name:' not in frontmatter:
        return False, "Missing 'name' in frontmatter"
    if 'description:' not in frontmatter:
        return False, "Missing 'description' in frontmatter"

    # Extract and validate name
    name_match = re.search(r'name:\s*(.+)', frontmatter)
    if name_match:
        name = name_match.group(1).strip()
        # Remove quotes if present
        name = name.strip('"').strip("'")
        # Check naming convention (hyphen-case: lowercase with hyphens)
        if not re.match(r'^[a-z0-9-]+$', name):
            return False, f"Name '{name}' should be hyphen-case (lowercase letters, digits, and hyphens only)"
        if name.startswith('-') or name.endswith('-') or '--' in name:
            return False, f"Name '{name}' cannot start/end with hyphen or contain consecutive hyphens"
        # Check name matches directory name
        if name != skill_path.name:
            safe_print(f"  Warning: Skill name '{name}' does not match directory name '{skill_path.name}'")

    # Extract and validate description
    desc_match = re.search(r'description:\s*(.+)', frontmatter)
    if desc_match:
        description = desc_match.group(1).strip()
        # Check for angle brackets
        if '<' in description or '>' in description:
            return False, "Description cannot contain angle brackets (< or >)"
        # Check description is not too short
        if len(description) < 20:
            return False, f"Description too short ({len(description)} chars). Need at least 20 characters."
        # Check for TODO placeholders
        if 'TODO' in description:
            return False, "Description contains TODO placeholder"

    # Check for unfilled template placeholders in body
    body = content[match.end():]
    placeholders = re.findall(r'\{[^}]+\}', body)
    # Filter out legitimate curly brace usage
    real_placeholders = [p for p in placeholders if any(
        keyword in p.lower() for keyword in [
            'skill_name', 'novel_title', '维度', 'fill', '填入',
            'skill name', 'novel title', 'insert'
        ]
    )]
    if real_placeholders:
        return False, f"Found unfilled template placeholders: {real_placeholders[:5]}"

    return True, "Skill is valid!"


def package_skill(skill_path, output_dir=None):
    """
    Package a skill folder into a zip file.

    Args:
        skill_path: Path to the skill folder
        output_dir: Optional output directory for the zip file (defaults to parent of skill folder)

    Returns:
        Path to the created zip file, or None if error
    """
    skill_path = Path(skill_path).resolve()

    # Validate skill folder exists
    if not skill_path.exists():
        safe_print(f"[ERROR] Error: Skill folder not found: {skill_path}")
        return None

    if not skill_path.is_dir():
        safe_print(f"[ERROR] Error: Path is not a directory: {skill_path}")
        return None

    # Validate SKILL.md exists
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        safe_print(f"[ERROR] Error: SKILL.md not found in {skill_path}")
        return None

    # Run validation before packaging
    safe_print("Validating skill...")
    valid, message = validate_skill(skill_path)
    if not valid:
        safe_print(f"[ERROR] Validation failed: {message}")
        safe_print("   Please fix the validation errors before packaging.")
        return None
    safe_print(f"[OK] {message}\n")

    # Determine output location
    skill_name = skill_path.name
    if output_dir:
        output_path = Path(output_dir).resolve()
        output_path.mkdir(parents=True, exist_ok=True)
    else:
        output_path = skill_path.parent

    zip_filename = output_path / f"{skill_name}.zip"

    # Create the zip file
    try:
        with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Walk through the skill directory
            for file_path in sorted(skill_path.rglob('*')):
                if file_path.is_file():
                    # Skip hidden files and system files
                    if any(part.startswith('.') and part not in ['.workbuddy'] for part in file_path.parts):
                        continue
                    if '__pycache__' in str(file_path):
                        continue
                    if file_path.suffix in ['.pyc', '.pyo']:
                        continue

                    # Calculate the relative path within the zip
                    # Include the skill directory name as top-level
                    arcname = file_path.relative_to(skill_path.parent)
                    zipf.write(file_path, arcname)
                    safe_print(f"  Added: {arcname}")

        safe_print(f"\n[OK] Successfully packaged skill to: {zip_filename}")
        return zip_filename

    except Exception as e:
        safe_print(f"[ERROR] Error creating zip file: {e}")
        return None


def main():
    if len(sys.argv) < 2:
        print("Usage: python build_skill.py <path/to/skill-folder> [output-directory]")
        print("\nExample:")
        print("  python build_skill.py output/xin-novel-style-santi")
        print("  python build_skill.py output/xin-novel-style-santi ./dist")
        sys.exit(1)

    skill_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None

    safe_print(f"Packaging skill: {skill_path}")
    if output_dir:
        safe_print(f"   Output directory: {output_dir}")
    safe_print("")

    result = package_skill(skill_path, output_dir)

    if result:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
