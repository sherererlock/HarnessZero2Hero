from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class Skill:
    """从 SKILL.md 中解析出的标准化技能结构。"""

    name: str = "Unknown Skill"
    description: str = "No description provided."
    body: str = ""


class SkillLoader:
    """从本地文件系统中加载并解析符合规范的技能模板。"""

    def __init__(self, work_dir: str) -> None:
        self.work_dir = Path(work_dir)

    def load_all(self) -> str:
        """扫描 .claw/skills 目录，解析所有 SKILL.md，并格式化为字符串。"""
        skill_base_dir = self.work_dir / ".claw" / "skills"
        if not skill_base_dir.exists():
            return ""

        chunks = [
            "\n### 可用专业技能 (Agent Skills)\n",
            "以下是你拥有的标准化外挂技能，请在符合 description 描述的场景下严格遵循其正文指令：\n\n",
        ]

        try:
            for path in skill_base_dir.rglob("SKILL.md"):
                if not path.is_file():
                    continue

                try:
                    content = path.read_text(encoding="utf-8")
                except OSError:
                    continue

                skill = parse_skill_md(content)
                chunks.append(f"#### 技能名称: {skill.name}\n")
                chunks.append(f"**触发条件**: {skill.description}\n\n")
                chunks.append("**执行指南**:\n")
                chunks.append(skill.body)
                chunks.append("\n\n---\n")
        except OSError:
            return ""

        rendered = "".join(chunks)
        if len(rendered) < 100:
            return ""
        return rendered


def new_skill_loader(work_dir: str) -> SkillLoader:
    return SkillLoader(work_dir)


def parse_skill_md(content: str) -> Skill:
    """解析带有 YAML frontmatter 的 Markdown 内容。"""
    skill = Skill(body=content)

    normalized = content.replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        return skill

    parts = normalized.split("---", 2)
    if len(parts) != 3:
        return skill

    frontmatter = parts[1].strip()
    body = parts[2].strip()

    try:
        metadata = yaml.safe_load(frontmatter) or {}
    except yaml.YAMLError:
        return skill

    if not isinstance(metadata, dict):
        metadata = {}

    return Skill(
        name=str(metadata.get("name", skill.name)).strip() or skill.name,
        description=str(metadata.get("description", skill.description)).strip() or skill.description,
        body=body,
    )
