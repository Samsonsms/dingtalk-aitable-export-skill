---
name: dingtalk-aitable-export
description: 通过钉钉官方 DWS CLI 将用户选中的一张 AI 表格原样导出为 Excel，保留原生表头及公式/引用计算值。适用于单表下载、拉取与归档，不用于整库导出、数据重拼或表格编辑。
---

# 钉钉 AI 表格原样导出

本技能自带 Python 3.12+ 标准库脚本，钉钉操作仅通过官方 `dws`，下载仅通过 Windows `curl.exe`。读取校验 XLSX ZIP/XML，不编辑、不重算、不重新保存。当前发布支持 Windows PowerShell。

## 正常流程

1. 先检查工作区规则和 Git 状态。找用户指定 `.env` 的 `DINGTALK_BASE_ID`（兼容 `baseId`）；只读此键，不显示其他配置。没有 `.env` 或 ID 时，提示用户从目标多维表右上角菜单进入“表格文档详情” → “基本信息”，复制“文档ID”后创建 `.env`；不要把文档链接当作 ID，也不要搜索并借用他人的配置。配置冲突时停止并询问。
2. 检查 `dws` 和 `curl.exe`；未安装时执行 `npm install -g dingtalk-workspace-cli`。运行 `dws auth status --format json`。未登录用 `dws auth login --device --recommend`，把真实授权链接交给用户完成，不能代替用户批准。有组织/账号歧义时先选明确账号；不可自动换账号。授权、版本兼容见 [运行手册](references/usage.md)。
3. 用脚本列出表名和 tableId，保存候选清单。默认排除含“测试”的表：
   ```powershell
   python "<skill-dir>/scripts/export_table.py" list --env-file ".env" --catalog "tmp/dingtalk-export/catalog.json"
   ```
   将全部候选以表格展示，**停下来等用户选一张**。不创建临时视图，不预下载。若本轮用户已在你展示的清单中明确选定，可以继续，不重复询问。
4. 选定后执行精确 tableId（来自清单），默认输出到当前工作区 `output/dingtalk_exports/<时间_随机后缀>/<表名>.xlsx`：
   ```powershell
   python "<skill-dir>/scripts/export_table.py" export --catalog "tmp/dingtalk-export/catalog.json" --table "<tableId>"
   ```
   脚本会核对账号、实时表名、完整字段目录，创建不指定名称的 Grid 临时视图，检查无筛选且全字段，按 `--scope view` 提交，只轮询同一 taskId，然后用 `curl.exe` 下载并删除该临时视图。不要另行使用 REST、record query、整库下载或 Excel 库重建数据。
5. 只有返回 `status=complete` 才报告成功。给出文件链接、Sheet 名称、数据行数、列数、表头样式、原字节 SHA256 和临时视图清理结果。公式/引用列是钉钉计算结果快照，不承诺保留可在 Excel 重算的钉钉公式。源错误/空值按原样保留并报告。

## 恢复与边界

- `status=pending` / 退出码 3：达到单次轮询上限；保留状态和临时视图，用返回的状态文件 `resume --state <state.json>` 续跑，禁止重建视图或重新提交任务。持续工作时每分钟给用户简短进度。
- 失败输出会给状态文件及清理结果；按 [故障恢复](references/recovery.md) 判断，不能把 unknown/partial 当成功。
- 临时视图清理已包含在用户明确的导出请求中，仅能删除本次状态中记录的 viewId。取消或恢复清理用 `cleanup --state <state.json>`；不按“表格视图”名称批量删除。
- 固定 profile 是当前实际账号，不代表该用户拥有库内所有表/字段权限。目录可见、记录可读、可建视图、可导出分别由钉钉校验；隐藏或筛选不是权限隔离。不要尝试绕过权限。
- 本技能可正常自动发现；安装和首次调用方法见 [运行手册](references/usage.md)。多账号可在 `list` 指定 `--profile <corpId>:<userId>`，后续从清单固定继承。
