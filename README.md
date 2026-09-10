# 钉钉 AI 表格原样导出 Skill

把“先列出表，等我选择，再下载单张原生 Excel”变成可分发技能。使用官方 DWS CLI 和临时全字段 Grid 视图，保留钉钉生成的文件字节，不通过 REST API 拉记录重拼 Excel。

版本：**1.0.0**。支持 **Windows PowerShell、Python 3.12+、Node.js/npm、官方 DWS、curl.exe**。脚本只使用 Python 标准库，无须第三方 Python 包。实测 DWS 版本和测试结果以 ZIP 内 `TEST_REPORT.json` 为准。

## 快速使用

1. 获取维护者测试通过的 ZIP 与 `.zip.sha256`，核对校验码后解压。
2. 在解压目录运行 `python install.py`；安装到当前用户的 Codex skills，已有同名技能时停止。
3. 在实际数据工作目录准备 `.env`，填写自己的 `DINGTALK_BASE_ID`。
4. 用自己的钉钉账号完成 `dws auth login --device --recommend`。
5. 在能识别该技能的新会话中输入：

   ```text
   使用 $dingtalk-aitable-export，读取当前工作目录的 .env，
   列出排除测试表的表名和 tableId，等我选择后原样导出。
   ```

完整步骤见 [安装与运行手册](skills/dingtalk-aitable-export/references/usage.md)，超时/失败见 [故障恢复](skills/dingtalk-aitable-export/references/recovery.md)。

## 输出与边界

- 单表 `.xlsx` 放在工作目录 `output/dingtalk_exports/<时间_随机后缀>/`，每次主动重新导出保留历史文件。
- 同目录 `state.json` 记录任务、账号范围和校验结果，支持恢复；它含本地业务元信息，不应分发。
- 检查单 Sheet/名称、全字段及顺序、表头底色和四边框、原字节摘要；报告公式/引用计算值及源错误。
- 下载后删除本次临时视图，不修改原表或已有视图。

“原样”指官方导出文件本身。临时视图使用默认样式，不承诺复制已有视图的自定义列宽、条件格式或筛选。公式/引用字段导出的是计算结果快照；空值和源错误不修补。

每个人使用自己的登录态，baseId 不提供授权。目录可见、记录可读、建视图和导出分别受服务端权限控制；隐藏/筛选不等于权限隔离。没有创建视图权限时停止，不降级整库导出。见 [权限与数据保护](docs/security.md)。

## 维护入口

```text
skills/dingtalk-aitable-export/   可安装技能本体
tests/                          合成数据离线测试
tools/                          测试、真实冒烟、发布与安装工具
docs/                           维护、安全与验收说明
tmp/                            本地测试证据，不入库
output/                         真实导出文件，不入库
dist/                           发布 ZIP 与校验码，不入库
```

阅读 [维护与发布](docs/maintenance.md)、[测试与验收](docs/testing.md)、[版本记录](CHANGELOG.md)。分发包用于运行；维护源码和测试在 Git 仓库中。没有配置自动远程发布或 Git push。

参考：[原手册与实现选择](docs/source-and-decisions.md)、[官方 DWS 项目](https://github.com/DingTalk-Real-AI/dingtalk-workspace-cli)。
