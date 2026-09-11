# 安装与使用

## 环境

支持 Windows 10/11 PowerShell、Python 3.12+ 和 Node.js/npm。Linux/macOS 不在本版验证范围内，下载明确使用 `curl.exe`。

```powershell
python --version
node --version
npm --version
curl.exe --version
npm install -g dingtalk-workspace-cli
dws --version
```

不必每次导出都升级 DWS。本版实测 v1.0.61；升级后重新执行离线和真实导出测试，不保证未来返回结构始终兼容。

## 安装技能

从可信维护者取得 ZIP 与 SHA256，先比对两者：

```powershell
Get-FileHash -Algorithm SHA256 '.\dingtalk-aitable-export-1.0.0.zip'
Get-Content '.\dingtalk-aitable-export-1.0.0.zip.sha256'
Expand-Archive -LiteralPath '.\dingtalk-aitable-export-1.0.0.zip' -DestinationPath '.\dingtalk-export-release'
Set-Location '.\dingtalk-export-release'
python install.py
```

安装器校验逐文件哈希，默认装到 `$CODEX_HOME/skills/dingtalk-aitable-export`；未设 `CODEX_HOME` 则是当前用户 `~/.codex/skills/dingtalk-aitable-export`。不会覆盖已有技能，不复制个人配置或登录态。

指定其他宿主的完整技能目录：

```powershell
python install.py --destination 'C:\your-skills\dingtalk-aitable-export'
```

其他支持 `SKILL.md` 的宿主可使用包内 `skills/dingtalk-aitable-export`，但未做这些宿主的实际集成验证。安装后开启新会话并显式调用 `$dingtalk-aitable-export`；已打开会话可能保留旧技能列表。

## 配置自己的 Base

打开目标钉钉多维表，点击右上角菜单，进入“表格文档详情” → “基本信息”，复制“文档ID”。然后在实际操作的工作目录建立 `.env`：

```dotenv
DINGTALK_BASE_ID=YOUR_BASE_ID
```

填写文档 ID，不要填写文档链接。兼容 `baseId=...`。两键同时存在必须一致，同名键重复会停止。支持引号、UTF-8 BOM 和行尾注释。不要写入 Token。无法查看文档详情时向表格拥有者确认，不能借用其他项目配置。

## 本人登录

```powershell
dws auth status --format json
dws auth login --device --recommend
```

已登录且认证有效不必重复登录。未登录时打开 CLI 实际返回的设备授权链接，批量权限确认链接也由本人打开完成；企业授权或资源权限不足按真实提示申请，不换成别人的账号。

多账号先核对组织和用户：

```powershell
dws profile list --format json
dws auth status --profile '<corpId>:<userId>' --format json
```

默认账号/组织不明确时先明确选择。脚本 `list --profile ...` 可指定账号；后续 export/resume/cleanup 从清单或状态固定继承，不随默认账号静默改变。

## 对 AI 说

第一次：

```text
使用 $dingtalk-aitable-export，读取我指定的 .env，列出所有不含“测试”的表名和 tableId，等我选定后只导出那一张表。
```

看到清单后回复一个精确表名或 tableId。同名表用 ID 消歧。列目录阶段不会创建视图；选定后才导出。

## 手动命令

在你的数据工作目录运行；设置了 `CODEX_HOME` 时相应调整 `$SkillPath`：

```powershell
$SkillPath = Join-Path $env:USERPROFILE '.codex\skills\dingtalk-aitable-export'
python "$SkillPath\scripts\export_table.py" list --env-file '.env' --catalog 'tmp/dingtalk-export/catalog.json'
python "$SkillPath\scripts\export_table.py" export --catalog 'tmp/dingtalk-export/catalog.json' --table '<清单中的tableId>'
```

已有清单不覆盖；重新列目录使用新的清单文件名。

| 命令 | 参数 | 行为 |
|---|---|---|
| list | --env-file、--catalog、可选 --profile | 保存候选，等用户选表 |
| export | --catalog、--table | 唯一精确表名或 tableId |
| export | 可选 --output | 归档根目录，默认 output/dingtalk_exports |
| export / resume | 可选 --max-polls | 默认 20，允许 1–120；每轮 DWS 等待 30 秒 |
| resume | --state | 原任务续跑；已完成时只检查文件摘要 |
| cleanup | --state | 精确清理本次视图，不删除 Excel |

每次主动 export 新建时间归档目录；resume 沿用原目录。Windows 文件名非法字符替换为下划线，Sheet 名仍须等于真实表名；钉钉若截断/改名导致校验失败，保留原文件报告，不改写。

成功 JSON 必须是 `status=complete` 且 `viewDeleted=true`，附文件与校验信息。源公式错误如实报告，不等于业务数据正确性校验通过。
