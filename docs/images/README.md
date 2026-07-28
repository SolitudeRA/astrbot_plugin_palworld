# PalWorldTerminal 文档图像

本目录保存 README 使用的正式图像。文件名是稳定接口，不使用方案号或版本号；中文位于本目录，
日文位于 `ja/`，英文位于 `en/`。

## 正式资产矩阵

| 资产 | zh-CN | ja | en | 原生尺寸 |
|---|---|---|---|---:|
| 多服务器连接 | `settings-servers.png` | `ja/settings-servers.png` | `en/settings-servers.png` | 2200×1920 |
| 功能启停树 | `settings-features.png` | `ja/settings-features.png` | `en/settings-features.png` | 2200×1920 |
| 管理员权限树 | `settings-permissions.png` | `ja/settings-permissions.png` | `en/settings-permissions.png` | 2200×1920 |
| 首次设置引导 | `settings-onboarding.png` | `ja/settings-onboarding.png` | `en/settings-onboarding.png` | 2200×1200 |
| 浅色图片名片 | `me-card-light.png` | `ja/me-card-light.png` | `en/me-card-light.png` | 1008×自然高度 |
| 暗色图片名片 | `me-card-dark.png` | `ja/me-card-dark.png` | `en/me-card-dark.png` | 1008×自然高度 |

另有不分语言的品牌资源：

| 文件 | 尺寸 | 用途 |
|---|---:|---|
| `logo.png` | 2048×2048 | 透明背景主 Logo |
| `banner.svg` | 1280×360 | README Banner 可编辑源文件 |
| `banner.png` | 1280×360 | README 完整 Banner |

## 唯一生成入口

先提交所有影响截图的源码、文案与生成工具，确认工作树除本目录外没有改动，再执行：

```powershell
$sourceCommit = git rev-parse HEAD
.\.venv\Scripts\python.exe scripts/capture_docs_assets.py --source-commit $sourceCommit
```

当前正式资产统一来自 source commit
`bf8b7091e003c8eaadcc08b8af3d70d557b2bebf`。完整文件清单、SHA-256、实际尺寸、场景参数及
Playwright/Chromium/Vite 版本记录在 `screenshots.manifest.json`。CI 只核对 manifest、哈希与
PNG IHDR，不在不同平台重建像素，也不要求 squash merge 后的主干 checkout 仍包含生成分支的
commit 对象；commit 的存在性、祖先关系与 source clean 状态由生成入口在替换资产前强制检查。

生成器先在临时目录完成全部 18 张图片及 manifest，全部校验通过后再替换本目录；失败时保留上一组
正式资产。不要手工修图、缩放或只替换其中一张。

## Scale 与可读性契约

- 设置页：1100px CSS viewport、DPR=2、visual viewport zoom=1，直接得到 2200px 宽 PNG；
  禁止截图后二次 resize。README 以 `width="100%"` 显示，在约 820px 内容宽下仍保留高密度字形。
- 图片名片：真实 `build_me_card_html` 使用 CSS `zoom: 2`，浏览器 DPR=1，直接得到 1008px 原生宽；
  高度随语言字体自然决定。README 两张并排各用 `width="49%"`。
- 每次生成后须在原图 100% 和约 820px README 内容宽下检查字形、抗锯齿、缺字、豆腐块、裁切、
  raw locale key、placeholder 与文字可读性。

## 确定性与隐私

设置页固定主题、locale、时钟、随机种子和演示场景；图片名片使用固定中性 `MeCardDTO` 与真实元素
SVG。示例身份仅使用 `Tokyo-01`、`Osaka-02`、`Seoul-03`、`operator-01`、`operator-02`、
`Ops A`、`Ops B` 和 `player-01` 等中性值，不含真实地址、凭证、用户标识或服务器数据。

## Banner 主配色

| 语义 | 色值 |
|---|---|
| 奶油天空 | `#FFF6DE` |
| 湖水浅蓝 | `#BCE9ED` |
| 深松绿 | `#285C4D` |
| 草木绿 | `#72B96A` |
| 暖金 | `#F4AD45` |
| 云朵白 | `#FFF9ED` |

Banner 的项目名使用 Segoe UI，`/pal` 字标使用 Consolas / Cascadia Mono 等宽字体。README 通过
相对路径以 `width="100%"` 显示 `banner.png`；修改 `banner.svg` 后，应重新导出同尺寸 PNG。
