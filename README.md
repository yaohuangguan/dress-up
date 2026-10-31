# 衣见 · Dress Up

本地 AI 搭配工具。选择人物、衣服和姿势，可选地点背景或文字描述，点击生成。ComfyUI 在后台运行，日常操作不需要编辑节点。

## 当前功能

- 桌面优先，玻璃质感悬浮导航；支持手机布局和可安装的 PWA。
- 13 位内置 AI 人物：6 位由本机生成，7 位来自用户提供的图片（其中四宫格原样拆为四张）。
- 1,407 套服装展示图、280 组姿势 / 1,158 张多视角线稿。
- 6 个内置地点：影棚、咖啡馆、城市街道、海岸、公园、室内。
- 人物、衣服、姿势、背景均可导入本地图片。背景还支持直接描述，留空使用影棚。
- 生成进度、记录、随机种子、图片下载和工作流导出。
- 手机拍照上传：短时二维码、一次性上传、桌面自动选中。独立上传端口不提供素材浏览或生图权限。

## 本机使用

双击 `Start-Studio.cmd`，打开 <http://127.0.0.1:7800>。双击 `Stop-Studio.cmd` 停止本项目服务。

ComfyUI 使用 8188 端口，工作台使用 7800，手机上传页按需使用 7801。本项目已经安装在当前电脑，直接启动即可。

## 新电脑安装

已验证环境：Windows、Python 3.11 x64、Git、RTX 2080 SUPER 8GB、32GB 内存。建议预留至少 30GB 可用空间。

1. 克隆仓库，安装 Python 3.11 和 Git。
2. 双击 `Setup.cmd`，下载锁定版本的依赖、ComfyUI、素材与官方模型（模型约 12.5GB，支持断点续传和 SHA-256 校验）。
3. 双击 `Start-Studio.cmd`。

运行时不需要第三方生图 API Key。推理使用本机 CUDA；文本编码放在 CPU，启用显存卸载和分块解码。模型和第三方整套图库通过安装脚本恢复；仓库包含内置人物、背景及其清单。

## 手机上传与 PWA

在人物页点击“扫码上传”，手机与电脑连同一 Wi-Fi 后扫码，可拍照或从相册选择图片。二维码 10 分钟有效，仅可使用一次。上传凭证放在 URL fragment 和请求头中，不进入 HTTP URL 日志。

跨设备连接还取决于本机防火墙和 Wi-Fi 隔离设置。本轮未修改 Windows 防火墙；实体手机的网络连通尚未实机验证。Cloudflare 外网入口按用户计划留待下一阶段。

PWA 可在桌面浏览器安装。离线缓存仅保存界面文件，不缓存用户照片；生图和素材服务需要本地进程持续运行。

## 验证

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
node --check web/app.js
node --check web/mobile.js
node --check web/sw.js
```

本机已运行 21 项自动测试。Edge 浏览器已检查五次导航切换、1500/1100/820/390 宽度、PWA、上传回传和桌面自动选中，无 JavaScript 错误或横向溢出。真实三图合成耗时 54.6 秒；加入地点的四图合成耗时 39.0 秒。耗时是本次测量，随输入、分辨率、缓存与显卡占用变化。

生成会受模型能力影响，人物和服装细节并非每次都完全一致。

## 来源与许可

- 姿势：[wquguru/shisei](https://github.com/wquguru/shisei)，图片与数据 CC0，保留许可和来源记录。
- 服装：[paipiange/nvzhuang](https://github.com/paipiange/nvzhuang)，原始作者为 ギア。镜像的 MIT 声明与原始图片条款存在差异；本项目保留两者记录，不把第三方服装图片重新声明为 MIT/CC0，也不在此仓库打包分发整套服装图片。见 `licenses/`。
- 模型：[FLUX.2 Klein 官方模型](https://huggingface.co/black-forest-labs/FLUX.2-klein-4b-fp8)，权重来源、修订与哈希见 `data/model-manifest.json`。
- 已按用户要求安装 [Agent Playbook](https://github.com/yaohuangguan/agent-playbook)，项目规则位于 `AGENTS.md`，技能位于 `.agents/skills/`。

## 后续计划

- Cloudflare 安全入口、身份与访问控制。
- 从当前成图进入 ComfyUI 图生视频工作流，设置动作、镜头、时长并保存视频。

上述两项尚未实现。
