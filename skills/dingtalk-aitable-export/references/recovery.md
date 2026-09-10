# 故障恢复

| 退出码 | 状态 | 处理 |
|---|---|---|
| 0 | selection_required | 展示清单，等待选表 |
| 0 | complete | 下载、校验、清理已确认 |
| 0 | cleaned | 检查 viewDeleted；无 viewId 不代表找到了未知创建的视图 |
| 3 | pending | 原状态续跑，不再提交新任务 |
| 1 | failed | 核查错误和状态，不将部分成功当完成 |

## 超时

```powershell
python '<skill-dir>/scripts/export_table.py' resume --state '<返回的state.json>'
```

已有 taskId 时，`TIMEOUT_ERROR` 继续轮询同一任务。每次调用默认最多 20 轮，每轮 DWS 等待 30 秒；达到上限返回 pending 并保留临时视图供续跑。不要以 export 代替 resume。

进程自身 90 秒超时、非法 JSON 或提交响应丢失，不等于远端没执行。`creating_view` 没有 viewId，或 `submitting_export` 没有 taskId 时，禁止重放写操作。先通过官方 CLI/界面核查真实结果；不能按“表格视图”名称批量删除，也不能猜 ID。未核清前暂停恢复。

## 下载失败

下载用 `curl.exe -L --fail`，仅允许 HTTPS。`.xlsx.part` 不算交付文件。失败会尝试清理已知视图，保留 taskId；resume 获取任务地址后重试下载。已有 `.xlsx` 没有匹配下载摘要时停止，绝不覆盖。

下载 URL 只在内存使用，不写 state/发布包。过期先 resume；远端任务失效时，保留原状态，核查清理后重新列目录选表。取消或清理了尚未完成任务的视图后，不保证远端任务仍有效。

## 清理失败或取消

```powershell
python '<skill-dir>/scripts/export_table.py' cleanup --state '<返回的state.json>'
```

只处理 state 的 viewId，删除前列视图确认；已不存在则记录清理成功。删除结果不明，本轮不重复删除，下次 cleanup 先读回。无权限则由本人/资源管理员解决。cleanup 不删除 Excel。

## 校验失败

保留文件，尽量清理临时视图。多 Sheet、名称不符、缺列/错序、缺底色/边框、无效 XLSX 或摘要变化都会失败；不通过重算、改样式或重拼制造通过结果。检查 DWS 版本、字段权限和官方输出变化。

## 中断与锁

`<state.json>.lock` 保存执行进程 PID，防止并发恢复。出现 State locked 时先读锁并用 `Get-Process -Id <pid>` 核实原进程。仍运行则等待；仅确认已停止且无其他持有者后，删除这个精确锁文件再 resume。不要递归清理输出目录。断电/强制结束可能留下视图，以 state 为恢复依据。

## 授权与日志

脚本不打印原始 CLI 错误、签名链接或 Token。需要授权链接时运行官方登录命令，交给用户本人完成。多账号不匹配时停止，不切换身份绕过。

校验只证明全字段视图、下载原字节、单表和样式，以及导出的计算值情况；不逐行查询全量源记录对账，不验证业务公式正确性，不证明其他账号权限配置。
