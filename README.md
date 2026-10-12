# Bambu Lab Filament Card Studio (耗材样本卡生成器)

一个专为 Bambu Lab 3D 打印机打造的耗材样本卡生成工具与 Web 应用。

支持从 Bambu Lab 官方商城链接自动抓取材质、颜色名、色号与 HEX 颜色，提供亚毫米级高保真排版预览，并一键生成兼容 Bambu Studio（支持 Prime Tower 擦料塔、100% Watertight 封闭网格）的 `.3mf` 模型文件。

---

## 特性亮点

- **自动解析商城链接**：粘贴任何 Bambu Lab 耗材页面链接（如 `https://us.store.bambulab.com/products/pla-wood?id=43075832086664`），自动提取产品类型、定位目标变体，并提取全页所有颜色药丸供一键切换。
- **内置 314 款官方耗材库**：无需联网抓取，直接搜索编号（如 `13106`）、中文名（如 `白橡木`）或英文名（如 `White Oak`）快速填入。
- **即时中英文切换**：一键切换中英文排版。
- **高保真矢量渲染预览**：采用系统原生 CJK 字体引擎（冬青黑体 / Arial Bold），精细自适应缩放与折行。
- **Bambu Studio 深度兼容**：
  - 卡体与浮雕文字组合为单个复合对象，统一层高，完美支持擦料塔（Prime Tower）。
  - 色块关联 AMS 换料槽。
  - 针对 0.4mm 喷嘴（Arachne 引擎）优化，提供形态学笔画加粗选项。

---

## 快速上手

### 1. 本地启动 WebApp

```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务
./start_webtool.sh
# 或
python3 app.py
```

在浏览器中打开：**`http://localhost:8088`**

### 2. 命令行直接生成 (CLI)

```bash
python3 make_filament_card.py "PLA WOOD" "White Oak" "(13106)" "#D6CCA3" 1.2 --preview
python3 make_filament_card.py "PLA WOOD" "白橡木" "(13106)" "#D6CCA3" 1.2 --preview
```

参数说明：
- `材料类型`：如 `"PLA WOOD"`、`"PLA MATTE"`
- `颜色名`：如 `"White Oak"`、`"白橡木"`
- `编号`：如 `"(13106)"`
- `HEX色号`：如 `"#D6CCA3"`
- `[浮雕高度mm]`：默认 `1.2` mm（`0.5` mm 为表面齐平嵌色）
- `--preview`：同时输出高清预览图

---

## 部署到 GitHub

本项目支持两种 GitHub 部署方式：

### 选项 A：GitHub Pages 纯静态部署（推荐，零服务器成本）
适合直接托管在 `https://<用户名>.github.io/<仓库名>`，依靠客户端浏览器直接解析、渲染并生成 3MF。

### 选项 B：完整仓库开源 + 一键云端托管
将仓库推送至 GitHub 后，可以一键部署到 Hugging Face Spaces / Vercel / Render 等平台，运行完整的 Python OpenCV 后端。
