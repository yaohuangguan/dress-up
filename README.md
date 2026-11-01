# 衣见 · Dress Up

本地 AI 搭配工具。选择人物、衣服和姿势，可选地点背景或文字描述，点击生成。ComfyUI 在后台运行，日常操作不需要编辑节点。

## 当前功能

- 桌面优先，玻璃质感悬浮导航；支持手机布局和可安装的 PWA。
- 13 位内置 AI 人物：6 位由本机生成，7 位来自用户提供的图片（其中四宫格原样拆为四张）。
- 另有 1,499 张 CC0 AI 人像预览，按发长检索；50 种去重发型可单独选择，也支持上传发型图或直接描述。预览图共约 28MB，不下载 4.86GB 原图包。
- 1,407 套服装展示图、280 组姿势 / 1,158 张多视角线稿。
- 6 个内置地点：影棚、咖啡馆、城市街道、海岸、公园、室内。
- 人物、衣服、姿势、背景、发型均可导入本地图片。背景还支持直接描述，留空使用影棚。
- 默认快速生成：FLUX.2 Klein 4B FP8、4 步、640×896 起，日常约一分钟。Base 50 步高清档只在手动选择时使用，本机实测约 6–10 分钟。
- 生成进度、记录、随机种子、图片下载和工作流导出。
- 手机拍照上传：短时二维码、一次性上传、桌面自动选中。独立上传端口不提供素材浏览或生图权限。
- 桌面和开始菜单“衣见”快捷方式，隐藏终端启动独立应用窗口。
- 带密码的 Cloudflare 临时 HTTPS 入口，计算仍由本机完成。
- 图生视频：约 3 / 5 秒动态片段；8 个独立分镜组成约 64 秒故事短片。
- Qwen3 4B 本地编剧、可编辑分镜、Kokoro 中文神经旁白、字幕、MP4 播放、下载和记录。

## 本机使用

双击桌面或开始菜单的“衣见”，会自动启动并打开独立窗口。也可双击 `Start-Studio.cmd`，打开 <http://127.0.0.1:7800>。双击 `Stop-Studio.cmd` 停止本项目服务和远程入口。

ComfyUI 使用 8188，工作台 7800，手机上传页按需使用 7801，远程认证网关 7802，编剧按需使用 7803。除独立手机上传页外均仅监听本机。服务的临时文件、Hugging Face 和 Torch 缓存默认放在项目 `work/` 中。编剧任务结束后卸载语言模型，图片和视频共用一个计算任务槽。

## 本机存放位置

本机项目专属文件统一放在 `E:/Coding/dress-up-workspace`，顶层“启动衣见.cmd / 停止衣见.cmd”可直接操作。程序、`.venv`、图库、作品及模型都在 `outputs/local-look-studio/` 内；模型实际位于 `runtime/ComfyUI/models/`。外层 `work/` 保存素材源库和开发工具。

旧 C 盘工作区及旧 E 盘模型位置仅留兼容链接，不存第二份模型。目录整理保留现有作品和记录，可整套搁置；后台服务可用停止脚本关闭。

## 新电脑安装

已验证环境：Windows、Python 3.11 x64、Git、RTX 2080 SUPER 8GB、32GB 内存。默认仅安装图片所需模型；图片安装建议预留至少 40GB 可用空间。

1. 在非系统盘（例如 `E:\Coding`）克隆仓库，安装 Python 3.11 和 Git。
2. 双击 `Setup.cmd`，下载锁定版本的依赖、ComfyUI、素材与图片模型（含精细/快速两套权重共约 16.5GB，支持断点续传和 SHA-256 校验）。不会下载视频、编剧或语音模型。
3. 双击 `Start-Studio.cmd`。

运行时不需要第三方生图 API Key。推理使用本机 CUDA；文本编码放在 CPU，启用显存卸载和分块解码。模型和第三方整套图库通过安装脚本恢复；仓库包含内置人物、背景及其清单。

## 独立发型

第五个选择位是可选发型；不选择、不填描述时保留人物原发型。内置 50 种发型从原站命名造型去重，使用发型描述改变造型，不把预览中的另一张脸作为额外身份参考。上传发型图则作为独立参考图。按照 Klein 官方最多 4 张参考的建议，同时选择背景图和上传发型图时，先生成搭配再调整发型，每轮均使用所选档位：快速档每轮 4 步，本机此组合实测 60.7 秒；手动高清档每轮 50 步，用时更长。内置发型采用描述，无需增加第二轮。生成仍可能影响人物五官或其他细节，不能视为严格局部替换。

人物库新增的 1,499 张均为虚构 AI 人像，当前使用 400px 浏览预览。人物身份和皮肤质感很依赖输入原片；需要更接近真实摄影时，优先导入清晰、无重度美颜的原照片。图库只提供素材，不会提升基础模型的能力。

安装脚本 `scripts/import_portraits.py` 从锁定版本的公开仓库稀疏检出缩略图；原站图片接口本机返回 403，因此未绕过原站限制。原图文件不随 Git 仓库分发，来源、版本、数量与体积见 `data/portrait-library-manifest.json`。

## 手机上传与 PWA

在人物页点击“扫码上传”，手机与电脑连同一 Wi-Fi 后扫码，可拍照或从相册选择图片。二维码 10 分钟有效，仅可使用一次。上传凭证放在 URL fragment 和请求头中，不进入 HTTP URL 日志。

直接 Wi-Fi 连接取决于本机防火墙和 Wi-Fi 隔离设置；本项目未修改 Windows 防火墙。也可在远程 HTTPS 入口登录后扫码上传，照片会经 Cloudflare 传输并存储在本机，生成计算仍在本机。

PWA 可在桌面浏览器安装。离线缓存仅保存界面文件，不缓存用户照片；生图和素材服务需要本地进程持续运行。

## 远程访问

运行 `.venv\Scripts\python.exe remote_access.py` 会建立带随机密码的 Cloudflare Quick Tunnel。链接和登录信息写在本机 `远程访问.txt`；`data/remote/` 保存凭证和进程状态，均被 Git 忽略。入口启用后，从桌面快捷方式启动也会自动恢复它。

这是临时地址，隧道重建后可能变化；电脑关机或服务停止时无法访问。Cloudflare 负责 HTTPS 转发，页面、上传照片与成图经其通道传输。页面、照片与 API 都经过身份验证；ComfyUI 不对公网开放。按用户当前选择，视频生成和播放先在本机完成，公网网关禁止转发视频文件。未部署 Pages 或 Workers。

## 故事短片

视频为可选模块。本机已按用户要求移除 LTX、T5、Qwen 编剧和 Kokoro 配音权重，保留已有作品和功能代码，不会自动下载。需要恢复时手动运行 `Setup.cmd --with-video`，额外下载约 12.3GB；当前未安装时生成按钮会禁用。

左侧悬浮导航点击“短片”，选择人物或已有成图。可直接使用《来自明天的消息》的完整分镜，也可填写主题并点击“AI 写分镜”，再展开调整旁白、画面与运镜。点击生成后，后台逐镜制作关键帧和视频，再加入本地神经中文旁白、字幕并剪辑。

默认视频为原生 512×704、24fps；故事是 8 个 193 帧镜头，约 64.3 秒。轻量 LTX 2B 适合试验，脸部、手部、快速动作与换景后的一致性会有偏差；这不等同于长镜头电影或口型同步对话。Qwen 4B 生成的剧本也需要编辑判断。中途失败的镜头和工作流保存在 `data/videos/<任务编号>/`，重启会把未完成任务标为中断，不会删除素材。

## 验证

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
node --check web/app.js
node --check web/video.js
node --check web/mobile.js
node --check web/sw.js
```

本轮运行 53 项自动测试，全部通过。新增检查覆盖画质档位、缺失模型、发型与背景排序、发型描述及视频模型安装必须主动选择；Edge 验证了五个选择位在 1500 / 1100 / 820 / 390 宽度下没有横向溢出，发型选择与描述可恢复。此前也检查了 PWA、手机上传和 MP4 播放。

此前本机已运行 39 项自动测试。Edge 浏览器检查了导航切换、1500/1100/820/390 宽度、PWA、上传回传、分镜编辑与真实 MP4 播放，无 JavaScript 错误或横向溢出。真实三图合成耗时 54.6 秒；加入地点的四图合成耗时 39.0 秒；首个 384×544、3.04 秒视频耗时 36.1 秒。8 镜头悬疑样片实测 64.33 秒、512×704、中文神经旁白与字幕，完整生成耗时 941.0 秒。耗时随输入、分辨率、缓存与显卡占用变化。

新精细档提高原生分辨率和采样步数，并明确区分人像肤色、服装材质和姿势关节参考。默认提示改为自然相机质感，减少美颜磨皮和塑料高光倾向，但提示本身不能保证真人级效果。它仍不提供严格的关节约束或服装分割，人物、肤色、手部与服装细节可能偏差。素材中的丝袜、夸张透视也会影响结果；高清尺寸不等于解剖或身份必然正确。

## 来源与许可

- 姿势：[wquguru/shisei](https://github.com/wquguru/shisei)，图片与数据 CC0，保留许可和来源记录。
- 服装：[paipiange/nvzhuang](https://github.com/paipiange/nvzhuang)，原始作者为 ギア。镜像的 MIT 声明与原始图片条款存在差异；本项目保留两者记录，不把第三方服装图片重新声明为 MIT/CC0，也不在此仓库打包分发整套服装图片。见 `licenses/`。
- 人像 / 发型：[あぎ原站](https://ai-portrait-gallery.pages.dev/)，CC0 1.0；预览与元数据来自 [RuiC-PoseAtlas](https://github.com/HRuiCcc/RuiC-PoseAtlas) 的公开版本。保留原站请求不要转载图片文件的说明，下载的图片不纳入本项目 Git 仓库。
- 图片模型：[FLUX.2 Klein Base 4B 官方模型](https://huggingface.co/black-forest-labs/FLUX.2-klein-base-4b-fp8)、[快速预览模型](https://huggingface.co/black-forest-labs/FLUX.2-klein-4b-fp8)，权重来源、修订与哈希见 `data/model-manifest.json`。
- 视频：[Lightricks LTX-Video](https://huggingface.co/Lightricks/LTX-Video)、[ComfyUI 原生示例](https://comfyanonymous.github.io/ComfyUI_examples/ltxv/)，版本和哈希见 `data/video-model-manifest.json`。使用 Lightricks 模型专有开放权重许可，不能把权重视为本项目许可证的一部分。
- 编剧：[Qwen3 4B GGUF](https://huggingface.co/Qwen/Qwen3-4B-GGUF)，Apache 2.0；运行程序 [llama.cpp](https://github.com/ggml-org/llama.cpp)，MIT。语音：[Kokoro 1.1-zh](https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh)，Apache 2.0。修订与哈希见 `data/creative-model-manifest.json`，第三方许可记录位于 `licenses/`。
- 已按用户要求安装 [Agent Playbook](https://github.com/yaohuangguan/agent-playbook)，项目规则位于 `AGENTS.md`，技能位于 `.agents/skills/`。

## 后续计划

- 固定远程域名、更强的视频模型、跨镜头一致性与分镜重试。
- 多人对话与口型同步。
