# GitHub Actions 部署指南（免费、24小时自动运行、电脑关机也能用）

## 原理

把代码上传到 GitHub 仓库，利用 GitHub 提供的 **Actions** 功能，每 30 分钟自动在云端服务器跑一次脚本。完全免费，不需要自己买服务器，电脑关机也不影响。

---

## 部署步骤（约 10 分钟）

### 第 1 步：注册/登录 GitHub

1. 打开 https://github.com
2. 有账号直接登录，没有就注册一个（免费）

### 第 2 步：创建新仓库

1. 登录后点右上角 **「+」** → **「New repository」**
2. 填写：
   - **Repository name**：随便填，比如 `hfuu-notice-monitor`
   - **Description**：可留空
   - 选 **Public**（公开，免费版也能用 Actions）或 **Private**（私有也行）
   - **不要勾选** "Add a README file"
3. 点底部 **「Create repository」**

### 第 3 步：上传代码文件

创建仓库后会看到一个空仓库页面，按下面操作：

1. 点页面中间的 **「uploading an existing file」** 链接
2. 打开本地的 `hfuu_notice_monitor` 文件夹，把**里面所有文件和文件夹**拖进去（包括 `.github` 文件夹）
   - 需要上传的文件：
     - `monitor.py`
     - `config.json`
     - `requirements.txt`
     - `seen_notices.json`（这个很重要，避免第一次运行推送所有历史通知）
     - `README.md`
     - `DEPLOY_GITHUB.md`
     - `.github/workflows/monitor.yml`（这个文件夹可能是隐藏的，注意要一起上传）
3. 拖进去后点底部 **「Commit changes」**

> **注意**：`.github` 文件夹在 Windows 上可能是隐藏的。如果拖拽上传看不到，可以在文件资源管理器地址栏直接输入 `.github` 进入，或者用 GitHub Desktop 上传。

### 第 4 步：配置飞书 Webhook（Secret）

这一步把飞书机器人地址配置到 GitHub，不会暴露在代码里：

1. 在仓库页面点顶部 **「Settings」**（设置）
2. 左侧菜单找到 **「Secrets and variables」** → 点 **「Actions」**
3. 点绿色按钮 **「New repository secret」**
4. 填写第一个：
   - **Name**：`FEISHU_WEBHOOK`
   - **Secret**：粘贴你的飞书机器人 Webhook 完整地址（`https://open.feishu.cn/open-apis/bot/v2/hook/xxxx`）
5. 点 **「Add secret」**

6. 如果你的飞书机器人开启了签名校验，再添加一个：
   - **Name**：`FEISHU_SECRET`
   - **Secret**：签名密钥
   - 没开启就跳过这步

7. （可选）如果想用 AI 智能总结，再添加：
   - **Name**：`AI_API_KEY`
   - **Secret**：火山引擎方舟 API Key
   - 不配置也能用，会自动用规则摘要

### 第 5 步：手动触发测试

1. 在仓库页面点顶部 **「Actions」**
2. 左侧会看到 **「学院通知监控」**，点它
3. 点右侧 **「Run workflow」** → 绿色按钮 **「Run workflow」**
4. 等十几秒，刷新页面，会看到一个黄色的运行任务
5. 点进去看日志，如果显示绿色对勾就是成功了
6. 去飞书群看看有没有收到测试消息（因为 seen_notices.json 已经记录了现有通知，第一次运行可能不会推送，属于正常）

> **想测试推送效果**：可以在本地把 `seen_notices.json` 里删掉一条记录，重新上传到 GitHub，然后手动触发，就会推送那条通知。

### 第 6 步：完成！

配置好之后，GitHub 会**每 30 分钟自动运行一次**，有新通知就推送到飞书。电脑关机也不影响。

---

## 常见问题

**Q: GitHub Actions 免费吗？会不会扣费？**
A: 公开仓库完全免费无限用。私有仓库每月有 2000 分钟免费额度，这个脚本每次运行不到 1 分钟，每天 48 次，每月约 1440 分钟，也够用。建议用公开仓库。

**Q: 每 30 分钟检查一次，能改频率吗？**
A: 可以。编辑 `.github/workflows/monitor.yml`，把 `cron: '*/30 * * * *'` 里的 30 改成你想要的分钟数（比如 `*/15` 就是每 15 分钟）。注意 GitHub 免费版最小间隔是 5 分钟。

**Q: 运行失败了怎么看日志？**
A: 仓库 → Actions → 点失败的任务 → 点 `monitor` → 展开各个步骤看红色报错信息。

**Q: 会重复推送同一条通知吗？**
A: 不会。`seen_notices.json` 记录了所有已推送的通知 URL，每次运行后自动更新并提交回仓库。

**Q: 学院网站改版了怎么办？**
A: 如果页面结构变了导致解析失败，脚本会在日志里提示"未解析到任何通知"。到时候告诉我，我帮你更新解析规则。

**Q: 想暂停监控怎么办？**
A: 仓库 → Settings → Actions → General → 选 "Disable Actions" 就停了。想恢复再打开。

---

## 文件结构

```
hfuu-notice-monitor/
├── .github/
│   └── workflows/
│       └── monitor.yml        # GitHub Actions 定时任务配置
├── monitor.py                  # 主程序
├── config.json                 # 默认配置（敏感信息用 Secrets 覆盖）
├── requirements.txt            # Python 依赖
├── seen_notices.json           # 已推送记录（自动更新）
├── README.md                   # 本地运行说明
└── DEPLOY_GITHUB.md            # 本文件（GitHub 部署说明）
```
