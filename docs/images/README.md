# PalWorldTerminal 美术资源

本目录只保留已确认的唯一正式版本，不使用方案号、版本号或主题后缀。

## 正式图像

| 文件 | 尺寸 | 用途 |
|---|---:|---|
| `logo.png` | 2048×2048 | 透明背景主 Logo |
| `banner.png` | 1280×480 | README 完整 Banner |
| `banner-background.png` | 1280×480 | 无 Logo、无文字的 Banner 背景 |

## Photoshop 母版

母版（`logo-master.psd`、`banner-master.psd`）**不入库**，另存于维护者私有云存储——避免仓库 archive 超出 AstrBot 插件市场 16MB zip 上限。

| 文件 | 结构 |
|---|---|
| `logo-master.psd` | 渐变底板、白色与绿色轨道、状态点、终端外壳、蓝色三角均独立分层，并附隐藏参考与规格说明 |
| `banner-master.psd` | 背景、Logo 阴影、完整嵌套 Logo 图层、分隔线三项元素和三层可编辑文字相互独立，并附隐藏参考与 12 条辅助线 |

Banner 背景是生成式插画，因此在 PSD 中作为单独的原始栅格层保留；Logo 与排版元素保持详细可编辑结构。

## 品牌色

| 语义 | 色值 |
|---|---|
| 深海军蓝 | `#0D2C4E` |
| 深青绿 | `#123023` |
| 信号绿 | `#279642` |
| 焦点蓝 | `#1D80D9` |
| 状态琥珀 | `#F5910E` |
| 暖白 | `#F3F1ED` |

Banner 的可编辑文字使用 Segoe UI Semibold 与 Microsoft YaHei。README 继续以 `width="640"` 显示 `banner.png`。
