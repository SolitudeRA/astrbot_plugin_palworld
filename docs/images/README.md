# PalWorldTerminal 美术资源

本目录中的 README 现用资源使用稳定文件名，不使用方案号、版本号或主题后缀。

## 正式图像

| 文件 | 尺寸 | 用途 |
|---|---:|---|
| `logo.png` | 2048×2048 | 透明背景主 Logo |
| `banner.svg` | 1280×360 | README Banner 可编辑源文件 |
| `banner.png` | 1280×360 | README 完整 Banner |
| `settings-servers.png` | 1100×960 | README 多服务器连接界面 |
| `settings-features.png` | 1100×960 | README 功能启停树 |
| `settings-permissions.png` | 1100×960 | README 管理员权限树 |
| `settings-onboarding.png` | 1100×600 | README 单服 / 多服首次设置引导 |

设置页截图由实际前端加载内置演示数据后生成；地址、账号标识和状态数据均为示例。

## Banner 主配色

| 语义 | 色值 |
|---|---|
| 奶油天空 | `#FFF6DE` |
| 湖水浅蓝 | `#BCE9ED` |
| 深松绿 | `#285C4D` |
| 草木绿 | `#72B96A` |
| 暖金 | `#F4AD45` |
| 云朵白 | `#FFF9ED` |

Banner 的项目名使用 Segoe UI，`/pal` 字标使用 Consolas / Cascadia Mono 等宽字体。README 通过相对路径以 `width="100%"` 显示 `banner.png`；修改 `banner.svg` 后，应重新导出同尺寸 PNG。
