#!/usr/bin/env python3
"""
Skill Builder & Packager - 校验并打包技能目录。

用法：
    python build_skill.py <skill目录> [输出目录]          # 校验 + 打包
    python build_skill.py <skill目录> --check             # 只校验，不打包
    python build_skill.py <父目录> --check                # 批量校验其下所有技能目录
    python build_skill.py <skill目录> --check --allow-placeholders   # 校验本构建器自身
    python build_skill.py <skill目录> --check --allow-name           # 用户点名要下划线名时

退出码：0 = 全部通过，1 = 有失败，2 = 用法错误。

为什么要这么严：
    2026-11 的女作者言情批次（29 个技能）里，21 个 name 用了中文弯引号「“x”」，
    3 个 description 用弯引号且没闭合、还漏了闭合的 `---` —— 整篇正文被当成
    frontmatter 吞掉，技能装上去等于空的。
    那批是绕过本脚本手动打的包。所以这里既把校验做狠，也把「跳过校验」这条路堵死。
"""

import argparse
import os
import re
import sys
import zipfile
from pathlib import Path

# frontmatter 只允许这些顶层键。多出来的（例如模型自作主张加的 `触发词:`）直接拒绝，
# 因为它们是「写坏 frontmatter」的早期信号。
ALLOWED_KEYS = {
    "name", "description", "agent_created", "keywords", "display_name",
    "version", "type", "author", "source", "tags", "read_when", "license",
}
CURLY_QUOTES = "\u201c\u201d\u2018\u2019"
MAX_DESCRIPTION = 400          # 字；本系列的技能集用的是 80，这里是通用上限
PLACEHOLDER_HINTS = (
    "skill_name", "novel_title", "维度", "fill", "填入",
    "skill name", "novel title", "insert",
)


def safe_print(message):
    """Print message safely, handling emoji encoding issues on Windows."""
    try:
        print(message)
    except UnicodeEncodeError:
        clean = re.sub(r"[\U0001F300-\U0001F9FF]", "", message)
        print(clean.strip())


if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def read_text_normalized(path):
    """读文件：去 BOM、统一成 LF。不依赖 Python 的通用换行，显式做一遍。"""
    raw = Path(path).read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    return raw.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")


def validate_skill(skill_path, allow_placeholders=False, allow_name=False):
    """校验单个技能目录。返回 (是否通过, 说明)。"""
    skill_path = Path(skill_path).resolve()
    name_on_disk = skill_path.name

    if not skill_path.is_dir():
        return False, "不是目录"
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        return False, "缺少 SKILL.md"

    content = read_text_normalized(skill_md)

    # ── 1. frontmatter 边界 ──────────────────────────────
    if not content.startswith("---\n"):
        if content.startswith("---"):
            return False, "首行必须是单独的 `---`（后面不能跟别的字符）"
        return False, "缺少 YAML frontmatter（文件必须以单独的 `---` 开头）"

    m = re.match(r"^---\n(.*?)\n---(?:\n|$)", content, re.S)
    if not m:
        return False, (
            "frontmatter 没有闭合：必须有另一行单独的 `---`。"
            "常见原因是 description 用了中文引号「“”」且没配对，把后面的内容全吞了"
        )
    fm, body = m.group(1), content[m.end():]

    # ── 2. 中文引号 ──────────────────────────────────────
    found = sorted({c for c in fm if c in CURLY_QUOTES})
    if found:
        line = next(l for l in fm.split("\n") if any(c in l for c in found))
        return False, (
            f"frontmatter 出现中文引号 {''.join(found)}，YAML 只认 ASCII 的 \" 和 '。"
            f"\n         出问题的行：{line[:80]}"
        )

    # ── 3. 键白名单 / 重复键 ─────────────────────────────
    # 逐行取顶层键：只用行首、非空、非缩进的行，这样中文键名（如 `触发词:`）也能被识别
    keys = []
    for line in fm.split("\n"):
        if not line or line[0] in " \t":
            continue
        km = re.match(r"^([^\s:]+)\s*:", line)
        if km:
            keys.append(km.group(1))

    unknown = [k for k in keys if k not in ALLOWED_KEYS]
    if unknown:
        return False, (
            f"frontmatter 含未知字段 {unknown}；只允许 {sorted(ALLOWED_KEYS)}。"
            "（例如 `触发词:` 应当写进 description 里，不能另起一个键）"
        )
    dup = sorted({k for k in keys if keys.count(k) > 1})
    if dup:
        return False, f"frontmatter 有重复字段 {dup}"

    for required in ("name", "description"):
        if required not in keys:
            return False, f"frontmatter 缺少 {required}"

    # ── 4. YAML 可解析性（装了 PyYAML 才查，不强制依赖）──
    try:
        import yaml  # type: ignore
        try:
            parsed = yaml.safe_load(fm)
        except Exception as e:
            first = str(e).split("\n")[0]
            return False, f"frontmatter 无法被 YAML 解析：{first}"
        if not isinstance(parsed, dict):
            return False, "frontmatter 解析结果不是键值对"
    except ImportError:
        parsed = None

    # ── 5. name ─────────────────────────────────────────
    name = None
    if isinstance(parsed, dict) and parsed.get("name") is not None:
        name = str(parsed["name"]).strip()
    else:
        nm = re.search(r"^name:\s*(.+)$", fm, re.M)
        name = nm.group(1).strip() if nm else None
        if name:
            name = name.strip("\"'")
    if not name:
        return False, "name 字段为空"
    name_pattern = r"[a-z0-9_-]+" if allow_name else r"[a-z0-9-]+"
    if not re.fullmatch(name_pattern, name):
        hint = "（已加 --allow-name，下划线允许，但其他字符仍不允许）" if allow_name else ""
        return False, (
            f"name '{name}' 只能用小写字母、数字、连字符（hyphen-case）{hint}；"
            "若带了引号请确认是 ASCII 的 \" 或 '"
        )
    if name.startswith("-") or name.endswith("-") or "--" in name:
        return False, f"name '{name}' 不能以连字符开头/结尾，也不能有连续连字符"
    if name != name_on_disk:
        return False, f"name '{name}' 与目录名 '{name_on_disk}' 不一致（必须完全相同）"

    # ── 6. description ──────────────────────────────────
    desc = None
    if isinstance(parsed, dict) and parsed.get("description") is not None:
        desc = str(parsed["description"]).strip()
    else:
        dm = re.search(r"^description:\s*(.+)$", fm, re.M)
        desc = dm.group(1).strip() if dm else None
    if not desc:
        return False, "description 为空"
    if desc in ("|", ">", "|-", ">-"):
        return False, "description 不能用多行块（| 或 >），必须是单行"
    if "<" in desc or ">" in desc:
        return False, "description 不能包含尖括号 < >"
    if "TODO" in desc:
        return False, "description 里还有 TODO"
    if len(desc) > MAX_DESCRIPTION:
        return False, f"description 过长（{len(desc)} 字 > 上限 {MAX_DESCRIPTION}），请压缩"
    if len(desc) < 20:
        return False, f"description 过短（{len(desc)} 字），至少 20 字才够触发"

    # ── 7. 占位符 ───────────────────────────────────────
    if not allow_placeholders:
        hits = [p for p in re.findall(r"\{[^}]+\}", body)
                if any(k in p.lower() for k in PLACEHOLDER_HINTS)]
        if hits:
            return False, f"正文还有未替换的模板占位符 {hits[:5]}"

    return True, "通过"


def collect_skill_dirs(target):
    """目标是技能目录就返回它自己；是父目录就返回其下所有含 SKILL.md 的子目录。"""
    target = Path(target).resolve()
    if (target / "SKILL.md").exists():
        return [target]
    if target.is_dir():
        return sorted(d for d in target.iterdir() if d.is_dir() and (d / "SKILL.md").exists())
    return []


def check_many(target, allow_placeholders=False, allow_name=False):
    dirs = collect_skill_dirs(target)
    if not dirs:
        safe_print(f"[ERROR] 没找到任何含 SKILL.md 的目录：{target}")
        return False

    failures = []
    for d in dirs:
        ok, msg = validate_skill(d, allow_placeholders, allow_name)
        if ok:
            safe_print(f"  [OK]   {d.name}")
        else:
            safe_print(f"  [FAIL] {d.name}\n         {msg}")
            failures.append(d.name)

    total = len(dirs)
    if failures:
        safe_print(f"\n结果：{total - len(failures)}/{total} 通过，{len(failures)} 个失败")
        safe_print("      修完再打包。不允许为了绕过校验而手动 zip。")
        return False
    safe_print(f"\n结果：{total}/{total} 全部通过")
    return True


def package_skill(skill_path, output_dir=None, allow_placeholders=False, allow_name=False):
    skill_path = Path(skill_path).resolve()

    if not skill_path.exists():
        safe_print(f"[ERROR] 技能目录不存在：{skill_path}")
        return None
    if not skill_path.is_dir():
        safe_print(f"[ERROR] 不是目录：{skill_path}")
        return None
    if not (skill_path / "SKILL.md").exists():
        safe_print(f"[ERROR] 缺少 SKILL.md：{skill_path}")
        return None

    safe_print("校验中…")
    ok, msg = validate_skill(skill_path, allow_placeholders, allow_name)
    if not ok:
        safe_print(f"[ERROR] 校验未通过：{msg}")
        safe_print("        修完再打包；不允许跳过校验直接手动 zip。")
        return None
    safe_print(f"[OK] {msg}\n")

    skill_name = skill_path.name
    if output_dir:
        output_path = Path(output_dir).resolve()
        output_path.mkdir(parents=True, exist_ok=True)
    else:
        output_path = skill_path.parent

    zip_filename = output_path / f"{skill_name}.zip"
    try:
        with zipfile.ZipFile(zip_filename, "w", zipfile.ZIP_DEFLATED) as zipf:
            for file_path in sorted(skill_path.rglob("*")):
                if not file_path.is_file():
                    continue
                if any(p.startswith(".") and p not in [".workbuddy"] for p in file_path.parts):
                    continue
                if "__pycache__" in str(file_path):
                    continue
                if file_path.suffix in [".pyc", ".pyo"]:
                    continue
                zipf.write(file_path, file_path.relative_to(skill_path.parent))
                safe_print(f"  Added: {file_path.relative_to(skill_path.parent)}")
        safe_print(f"\n[OK] 已打包：{zip_filename}")
        return zip_filename
    except Exception as e:
        safe_print(f"[ERROR] 打包失败：{e}")
        return None


def main():
    ap = argparse.ArgumentParser(
        add_help=True,
        description="校验并打包技能目录（frontmatter 严格校验）",
    )
    ap.add_argument("path", help="技能目录，或其父目录（批量校验）")
    ap.add_argument("outdir", nargs="?", default=None, help="zip 输出目录，默认与技能同级")
    ap.add_argument("--check", action="store_true", help="只校验，不打包")
    ap.add_argument("--allow-placeholders", action="store_true",
                    help="允许未替换的模板占位符（只给打包本构建器自身用）")
    ap.add_argument("--allow-name", action="store_true",
                    help="允许 name 含下划线（用户点名要求时用；仍强制 name 与目录名一致）")
    args = ap.parse_args()

    if args.check:
        safe_print(f"校验：{args.path}\n")
        sys.exit(0 if check_many(args.path, args.allow_placeholders, args.allow_name) else 1)

    safe_print(f"打包：{args.path}")
    if args.outdir:
        safe_print(f"   输出目录：{args.outdir}")
    safe_print("")
    result = package_skill(args.path, args.outdir, args.allow_placeholders, args.allow_name)
    sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()
