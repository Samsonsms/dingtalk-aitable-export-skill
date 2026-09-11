# 钉钉 AI 表格单表原样导出

从一个钉钉 AI 表格库中列出可导出的表，等你选定后，将其中一张表下载为钉钉官方生成的 Excel。

- 先展示候选清单，不默认选择第一张表
- 每次只导出一张表，不下载整个 Base
- 不修改原表、业务数据或已有视图
- 保留官方导出的表头及公式、引用字段的计算结果
- 支持超时续跑，并精确清理本次创建的临时视图

> 当前版本：**1.0.0**。支持 Windows 10/11 PowerShell、Python 3.12+、Node.js/npm、官方 DWS CLI 和 `curl.exe`。

## 适用范围

适合：

- 下载钉钉 AI 表格库中的一张指定表
- 归档钉钉官方生成的原生 `.xlsx` 文件
- 需要明确选表、结果校验和失败恢复的自动化流程

不适合：

- 导出整个 Base 或批量导出多张表
- 修改表格、字段、记录或已有视图
- 查询记录后重新拼装 Excel
- 复制已有视图的全部视觉配置

## 快速开始

### 1. 安装技能

仓库地址：

```text
https://github.com/Samsonsms/dingtalk-aitable-export-skill
```

需要安装的是仓库中的 `skills/dingtalk-aitable-export/` 子目录，不是整个仓库。以下提示词可以直接复制给对应 Agent。

#### Codex

```text
使用 $skill-installer 安装：
https://github.com/Samsonsms/dingtalk-aitable-export-skill/tree/codex/initial-release/skills/dingtalk-aitable-export
```

Skill Installer 会从 GitHub 获取指定目录并写入当前用户的 Codex skills 目录；如果已经存在同名技能会停止，不会覆盖现有版本。安装完成后开启新会话，让 Codex 重新加载技能列表。

#### Claude Code

```text
请通过 Git 安装这个 Agent Skill：
https://github.com/Samsonsms/dingtalk-aitable-export-skill/tree/codex/initial-release/skills/dingtalk-aitable-export

只复制仓库中的 skills/dingtalk-aitable-export 目录到
~/.claude/skills/dingtalk-aitable-export。
如果目标目录已存在，停止并报告，不要覆盖。安装后检查目标目录下存在 SKILL.md。
```

Claude Code 的个人 Skill 目录是 `~/.claude/skills/<skill-name>/`，安装后可以通过 `/dingtalk-aitable-export` 显式调用。参见 [Claude Code Skills 文档](https://code.claude.com/docs/en/slash-commands)。

#### DeepSeek Harness

```text
请通过 Git 安装这个 Agent Skill：
https://github.com/Samsonsms/dingtalk-aitable-export-skill/tree/codex/initial-release/skills/dingtalk-aitable-export

只复制仓库中的 skills/dingtalk-aitable-export 目录到
~/.dsh/skills/dingtalk-aitable-export。
不要使用 dsh plugin add；这是 Skill，不是 Plugin。
如果目标目录已存在，停止并报告，不要覆盖。安装后检查目标目录下存在 SKILL.md。
```

DeepSeek Harness 也会发现 `~/.agents/skills/dingtalk-aitable-export/`，适合与其他兼容 Agent 共享同一份安装。参见 [DeepSeek Harness Skills 文档](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/skills.md)。

> Claude Code 和 DeepSeek Harness 的说明只覆盖 Skill 文件结构与发现路径。当前版本的完整导出流程只在 Windows PowerShell 与 Codex 环境完成真实 CLI 冒烟测试。

### 2. 准备自己的 AI 表格 ID

在实际处理数据的工作目录中创建 `.env`：

```dotenv
DINGTALK_BASE_ID=YOUR_BASE_ID
```

`baseId` 只用于定位目标 AI 表格库，不会授予额外权限。请使用自己的 Base ID，不要把 Token 写入 `.env`。

### 3. 登录官方 DWS

```powershell
dws auth status --format json
dws auth login --device --recommend
```

使用你自己的钉钉账号完成设备授权。技能不会替你批准授权，也不会切换账号绕过权限。

### 4. 调用技能

打开能识别该技能的新会话，然后输入：

```text
使用 $dingtalk-aitable-export，读取当前工作目录的 .env，
列出排除测试表的表名和 tableId，等我选择后只导出那一张表。
```

技能会先返回候选清单并停止。回复一个精确表名或 `tableId` 后，才会开始导出。

完整参数和手动命令见[安装与运行手册](skills/dingtalk-aitable-export/references/usage.md)，超时或失败处理见[故障恢复](skills/dingtalk-aitable-export/references/recovery.md)。

## 导出过程中会发生什么

```text
读取 Base ID 和当前登录身份
        ↓
列出候选表，等待你选择
        ↓
为选定表创建一个临时全字段 Grid 视图
        ↓
通过官方 DWS 提交单表导出并下载 Excel
        ↓
校验文件并删除本次临时视图
```

临时视图只在选表后创建。技能只删除状态文件中记录的本次 `viewId`，不会按名称批量删除视图。

## “原样”是什么意思

“原样”表示保留钉钉官方导出文件的原始字节，不通过 REST API 查询记录后重建、重算或重新保存 Excel。

技能会检查：

- 只有一个 Sheet，且 Sheet 名与所选表一致
- 字段完整、顺序一致
- 表头包含底色和四边框
- 下载文件的 SHA256 在处理过程中未变化
- 公式和引用字段的计算结果及源错误得到如实报告

“原样”不表示复制某个已有视图的全部外观。临时视图使用默认样式，不承诺保留已有视图的自定义列宽、条件格式或筛选配置。公式和引用字段导出的是当前计算结果快照，不承诺在 Excel 中继续使用钉钉公式重算。

## 输出与恢复

每次主动导出会创建独立目录：

```text
output/dingtalk_exports/<时间_随机后缀>/
├── <表名>.xlsx
└── state.json
```

`state.json` 保存账号范围、表、任务和校验状态，用于安全续跑。它包含本地业务元信息，不应提交或分发。

只有返回 `status=complete` 才代表导出、校验和临时视图清理全部完成。超时返回 `status=pending` 时，应使用原状态文件继续轮询同一个任务，不能重新创建视图或重复提交导出。

## 权限与数据保护

- 每个人使用自己的 DWS 登录态和服务端权限
- 目录可见不代表拥有全部记录、建视图或导出权限
- 隐藏和筛选不是权限隔离
- 没有创建视图权限时停止，不改用管理员账号或整库导出
- `.env`、状态文件、导出文件、账号信息和下载签名 URL 不进入发布包

详细说明见[权限与数据保护](docs/security.md)。

## 开发与维护

```text
skills/dingtalk-aitable-export/   可安装技能本体
tests/                            合成数据离线测试
tools/                            检查、真实冒烟、发布和安装工具
docs/                             维护、安全与验收说明
tmp/                              本地测试证据，不入库
output/                           真实导出文件，不入库
dist/                             发布 ZIP 与校验码，不入库
```

维护者应阅读：

- [维护与发布](docs/maintenance.md)
- [测试与验收](docs/testing.md)
- [实现依据与选择](docs/source-and-decisions.md)
- [版本记录](CHANGELOG.md)

项目没有配置自动远程发布或 Git push。官方 CLI 参考见 [DingTalk Workspace CLI](https://github.com/DingTalk-Real-AI/dingtalk-workspace-cli)。
