# Xin Novel Style Builder · 小说写作风格 Skill 构建器

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

一个端到端的 AI 写作风格 Skill 构建工具：输入小说正文（文件路径或粘贴文本），自动清洗并提取前 20 章纯净正文，从 **十个维度** 深度萃取写作风格，生成标准格式的「文风锁定 Skill」，并打包为可直接导入的 zip 安装包。

> 让 AI 以目标小说的语感创作全新内容，只仿文笔、不抄剧情。

---

## 功能特性

- **自动提取纯净正文**：识别中/英文章节标记，提取前 20 章正文，自动剔除书名、简介、书评、版权声明等非正文内容（支持 txt / md / docx）
- **十维文风萃取**：叙事视角、句式特征、对话体系、叙事节奏、词汇与修辞、情绪基调、章节钩子写法、环境描写、行文禁忌、开篇习惯
- **标准 Skill 输出**：生成带 YAML frontmatter 的 `SKILL.md` 与使用说明 `readme.md`，十维结论全部填入、不留占位符
- **一键打包**：内置 `build_skill.py` 打包脚本，自动校验格式（frontmatter、hyphen-case 命名、description 合法性）并生成可导入的 zip
- **可独立使用**：生成的文风 Skill 不依赖本构建器，安装后即可直接指导 AI 创作
- **版权安全**：严格模仿文笔、叙事节奏、语感，严禁抄袭、复述原书剧情

## 工作原理

构建器按 5 步流水线工作：

```mermaid
flowchart LR
    A[输入小说内容] --> B[提取与清洗<br/>前20章纯净正文]
    B --> C[十维文风萃取]
    C --> D[生成文风锁定Skill<br/>SKILL.md + readme.md]
    D --> E[打包为可导入 zip]
```

1. **输入收集与命名确认** — 接收文件或粘贴文本，确认 Skill 名称（默认自动生成 `xin-novel-style-[关键词]`，中文名自动转拼音）
2. **内容提取与清洗** — 识别章节标记，提取前 20 章，剔除简介、书评、meta 信息等非正文内容
3. **十维文风萃取** — 逐维度分析样本，结论具象化、可执行，所有结论基于正文、禁止凭空想象
4. **生成文风锁定 Skill** — 按 `assets/skill_template.md` 填充十维萃取结果，生成 `SKILL.md`；按 `assets/readme_template.md` 生成使用说明 `readme.md`
5. **打包为 zip** — 运行 `scripts/build_skill.py` 验证并打包

## 目录结构

```
xin-novel-style-builder/
├── SKILL.md                        # 本构建器 Skill 主文件（含完整工作流与硬性规则）
├── assets/
│   ├── skill_template.md           # 文风锁定 Skill 的标准输出模板
│   └── readme_template.md          # 使用与仿写说明模板（500 字以内）
├── references/
│   └── extraction_framework.md     # 十维萃取框架详细指引（每个维度的分析要点与示例）
└── scripts/
    └── build_skill.py              # Skill 校验与打包脚本
```

## 安装本构建器

- **方式一（zip 导入）**：下载 `xin-novel-style-builder.zip` 并解压，将 `xin-novel-style-builder` 文件夹放入技能目录（如 `~/.workbuddy/skills/` 或项目级 `.workbuddy/skills/`），重启生效
- **方式二（克隆仓库）**：`git clone` 本仓库，将 `xin-novel-style-builder` 目录放入技能目录

> 本 Skill 遵循通用 Skill 格式（`SKILL.md` + YAML frontmatter），支持该格式的 agent 技能系统均可导入。

## 使用方法

### 触发词

`生成小说风格skill` · `小说文风构建` · `文风skill生成器` · `novel style builder` · `小说风格提取打包` · `xin-novel-style`

### 示例

```
请帮我从 C:\novels\santi.txt 生成一个文风 skill，名称叫 xin-novel-style-santi
```

构建器将输出到当前工作目录的 `output/` 文件夹：

```
output/
├── xin-novel-style-santi/     # 生成的文风锁定 Skill 目录
├── xin-novel-style-santi.zip  # 可导入的 Skill 安装包
└── readme.md                  # 使用与仿写说明（与 zip 同级，不打进 zip）
```

导入生成的 zip 后，即可对 AI 说「按 XX 文风写……」触发仿写，输出为纯净小说正文。

## 打包脚本（开发者）

```bash
# 用法
python scripts/build_skill.py <skill-folder> [output-dir]

# 示例
python scripts/build_skill.py output/xin-novel-style-santi
python scripts/build_skill.py output/xin-novel-style-santi ./dist
```

脚本自动执行：

1. 验证 `SKILL.md` 存在且含合法 YAML frontmatter（`name` / `description` 必填）
2. 验证名称符合 hyphen-case 规范（仅小写字母、数字、连字符）
3. 校验 description 无尖括号、长度达标、无 TODO 占位符
4. 将整个 Skill 目录打包为 zip，zip 内保留 Skill 目录名作为顶层目录

> **注意**：打包本构建器自身时，`SKILL.md` 中作为示例的模板占位符（`{SKILL_NAME}`、`{NOVEL_TITLE}`）会被误判为「未填充占位符」而拒绝打包。此时请手动打包，保留 `xin-novel-style-builder` 作为顶层目录名，并排除隐藏文件。

## 依赖

- **Python 3**（仅标准库，用于 `build_skill.py`）
- **python-docx**（可选，仅读取 docx 格式小说时使用）

## 注意事项与版权

- 本工具只萃取与模仿「文笔、叙事节奏、语感」，**严禁抄袭、复述原书剧情**
- 生成的文风 Skill 不包含原书正文内容（`style_examples.md` 仅为风格佐证片段）
- 请仅对你有权处理的小说内容进行风格萃取，尊重原作者版权

## License

[MIT](LICENSE)
