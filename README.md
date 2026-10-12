# Bambu Lab Filament Card Studio (耗材样本卡生成器)

专为 Bambu Lab 3D 打印机打造的耗材样本卡生成工具与 Web 静态应用，已支持 **GitHub Pages 纯前端免服务器部署**！

🌐 **在线体验 (GitHub Pages)**: [https://ziikki.github.io/filament_card/](https://ziikki.github.io/filament_card/)

---

## 🌟 核心特性

- **100% 浏览器纯前端运行 (GitHub Pages)**：
  - 无需安装 Python 或任何运行环境，直接在浏览器里读取模板、实时剖分网格、打包生成并下载 `.3mf` 文件。
  - 零服务器成本，手机与电脑浏览器即开即用。
- **默认 0.5mm 平齐嵌色（Flush Multi-color Inlay）**：
  - 默认浮雕高度为 `0.5 mm`，打印出来的样本卡文字、色块与卡体表面完全平齐，触感平整丝滑。
  - 也可自由调节为 `1.2 mm` 凸起立体浮雕。
- **自动解析商城链接**：
  - 粘贴任何 Bambu Lab 耗材页面链接（如 `https://us.store.bambulab.com/products/pla-wood?id=43075832086664`），自动识别产品类型与目标颜色，并列出全系列颜色药丸供一键切换。
- **内置 314 款官方耗材库**：
  - 无需联网抓取，直接搜索编号（如 `13106`）、中文名（如 `白橡木`）或英文名（如 `White Oak`）快速填入。
- **即时中英文切换**：一键切换中英文排版。
- **Bambu Studio 深度兼容**：
  - 卡体与浮雕文字组合为单个复合对象，统一层高，完美支持擦料塔（Prime Tower）。
  - 100% Watertight 封闭网格，官方 0.4mm 喷嘴优化。

---

## 🚀 推送到你的 GitHub 仓库并启用 GitHub Pages

### 1. 推送代码到 GitHub
在 GitHub 账号 [ziikki](https://github.com/ziikki) 下创建一个名为 **`filament_card`** 的公开仓库，然后在本地终端运行：

```bash
git remote add origin https://github.com/ziikki/filament_card.git
git branch -M main
git push -u origin main
```

*(如果已配置 remote，直接运行 `git push -u origin main` 即可)*

### 2. 启用 GitHub Pages
推送完成后，只需在 GitHub 仓库页面简单开启：
1. 进入仓库的 **Settings** -> 左侧菜单 **Pages**。
2. 在 **Build and deployment** 下的 **Source**：
   - 选择 **GitHub Actions**（本仓库已配置自动构建工作流 `.github/workflows/deploy.yml`，每次 push 自动发布），
   - 或者选择 **Deploy from a branch** -> 分支选择 `main` -> 目录选择 `/ (root)` -> 点击 **Save**。
3. 等待约 1 分钟，即可直接通过 **https://ziikki.github.io/filament_card/** 在线使用！

---

## 💻 本地运行与命令行 (CLI)

如果你想在本地离线运行：

### 本地启动 WebApp
```bash
./start_webtool.sh
# 或
python3 app.py
```
在浏览器中打开：**`http://localhost:8088`**

### 命令行直接生成 (CLI)
```bash
python3 make_filament_card.py "PLA WOOD" "White Oak" "(13106)" "#D6CCA3" 0.5 --preview
python3 make_filament_card.py "PLA WOOD" "白橡木" "(13106)" "#D6CCA3" 0.5 --preview
```
参数说明：
- `材料类型`：如 `"PLA WOOD"`、`"PLA MATTE"`
- `颜色名`：如 `"White Oak"`、`"白橡木"`
- `编号`：如 `"(13106)"`
- `HEX色号`：如 `"#D6CCA3"`
- `[浮雕高度mm]`：默认 `0.5` mm（表面齐平嵌色；输入 `1.2` mm 为突出表面）
- `--preview`：同时输出高清预览图
