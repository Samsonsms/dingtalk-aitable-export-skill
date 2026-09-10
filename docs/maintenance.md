# 维护与发布

Git 仓库是开发源；修改 `skills/dingtalk-aitable-export/`，不要只改本机安装目录。运行脚本只有标准库依赖。版本在导出脚本和 `tools/project_checks.py`，升版时同步 README、运行手册示例和 CHANGELOG。

## 发布顺序

在源码仓库目录执行：

```powershell
git status --short
python tools/check.py
python tools/live_smoke.py --env-file '<本人的.env完整路径>' --table '<已经选定的tableId或精确表名>'
python tools/release.py --install
```

真实冒烟会创建/删除一个临时视图并下载一张表，必须先明确已授权测试账号、库和表，不能默认第一张。目标应有公式、引用字段及非空计算值，以覆盖原样导出；仍排除名称含“测试”的表。没有合适授权表就停止发布，不伪造证据。

离线证据 `tmp/validation.json`、真实证据 `tmp/live_smoke.json` 绑定完整受维护源码清单的摘要。脚本、测试或文档变化都必须重测。真实文件缺失/改动、清理未完成、原视图改变，发布门禁会拒绝。

Codex 开发环境还应运行技能创建器自带的 `quick_validate.py`；路径依安装而异，不作为分发运行依赖。本仓库的结构校验检查名称、入口、Python 语法和 Markdown 本地链接，不代替行为测试。

发布工具生成 `dist/dingtalk-aitable-export-<版本>.zip` 和 `.zip.sha256`；`--install` 从该 ZIP 校验安装，省略则只打包。已有同版本 ZIP 不覆盖。发布报告脱敏，不含实际账号 ID、表名和数据。

## 升级、回滚、卸载

1. 先测试并打包新版本，保持旧安装可用。
2. 核实旧版绝对路径，把这个精确技能目录移动到 skills 目录外的版本备份位置。
3. 解压新 ZIP 运行 `python install.py`，安装器验文件哈希，不覆盖旧目录。
4. 核对安装文件与包一致，新会话显式调用。失败时保留新包并恢复已核实的旧目录。

不得覆盖用户自行修改的技能。卸载只移除/移出该技能的精确目录，不删除 DWS、登录态或导出数据。Windows 递归移动/删除前必须核对目标在预期路径内。

## 本地 Git 提交

```powershell
git diff --check
git status --short
git add .env.example .gitignore AGENTS.md README.md CHANGELOG.md skills tests tools docs
git diff --cached --stat
git commit -m "Preserve native single-table exports with verified recovery and release gates"
```

暂存区不得含 `.env`、真实 Excel、凭据或账号/业务配置。没有远端地址就不创建远端，不自动 push。

## 日常维护

| 触发 | 动作 |
|---|---|
| 报错 | 收集脱敏错误类别、DWS 版本、状态阶段、清理结果，不索要 Token |
| 返回结构变化 | 依据实际响应修解析并加回归测试，不放宽单表/原样要求 |
| 长时间 pending | 沿用 taskId，过期/失败按恢复手册处理 |
| 视图残留 | 用 state 精确 viewId 和原账号 cleanup |
| DWS 升级 | 重新离线与真实测试，更新兼容说明 |
| 新平台 | 完成真实平台验证后才扩大支持声明 |

未配置后台定时维护；后续维护依靠仓库规范和发布检查。
