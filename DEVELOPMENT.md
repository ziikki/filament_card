# 🛠️ Developer Reference & Internal Notes (开发与部署参考)

This document contains internal technical references, deployment instructions, architecture notes, and developer guides for **Bambu Lab Filament Card Studio**. 

These details are maintained separately from the user-facing `README.md` to keep the front page focused on end users.

---

## 📌 1. Git Repository & Push Configuration (推送仓库目标)

The upstream repository configuration:

| Item | Value |
| :--- | :--- |
| **GitHub User** | [`ziikki`](https://github.com/ziikki) |
| **Repository Name** | `filament_card` |
| **Repository URL** | `https://github.com/ziikki/filament_card` |
| **Remote Git URL** | `https://github.com/ziikki/filament_card.git` |
| **Target Branch** | `main` |

### Step-by-Step Push Instructions:
```bash
# 1. Check status and commit changes
git status
git add .
git commit -m "feat: your commit message"

# 2. Push to main branch
git push -u origin main
```

---

## 🚀 2. GitHub Pages Deployment (在线部署设置)

The web application runs **100% client-side** and requires no server runtime.

### Automated Deployment via GitHub Actions:
- The repository includes `.github/workflows/deploy.yml` which automatically builds and deploys on every push to `main`.
- To verify or configure:
  1. Go to repository **Settings** -> **Pages** in GitHub.
  2. Under **Build and deployment** -> **Source**, select **GitHub Actions**.
  3. The workflow will run and deploy to:
     - 🇺🇸 English: `https://ziikki.github.io/filament_card/`
     - 🇨🇳 Chinese: `https://ziikki.github.io/filament_card/zh.html`

---

## 📂 3. Repository Directory Structure (仓库目录结构)

```text
filament_card/
├── .github/workflows/deploy.yml  # GitHub Actions automated Pages deployment
├── .gitignore                    # Git ignore rules (caches, OS files)
├── README.md                     # User-facing documentation & showcase
├── DEVELOPMENT.md                # Developer reference & internal notes (this file)
├── index.html                    # English static web app (100% client-side)
├── zh.html                       # Chinese static web app (100% client-side)
├── card_template.3mf             # Base Bambu Studio 3MF template (0.1mm layer setup)
├── filament_db.json              # Database of 314 official Bambu Lab filaments
├── app.py                        # Local lightweight Python server & dev endpoints
├── make_filament_card.py         # Python CLI 3MF generator & watertight mesh builder
├── extractor.py                  # Bambu Lab official store URL scraper & parser
├── requirements.txt              # Python dependencies for local CLI / server
├── start_webtool.sh              # One-click startup script for local Python app
├── examples/                     # Sample cards & high-resolution preview renders
│   ├── card_whole_preview_3d.png           # Sliced 3D isometric render
│   ├── card_whole_preview_white_oak.png    # 75x36mm EN preview render
│   ├── card_whole_preview_zh_white_oak.png # 75x36mm ZH preview render
│   ├── Filament_Card_Lemon_Yellow.3mf      # Pre-generated sample 3MF
│   ├── Filament_Card_White_Oak.3mf         # Pre-generated sample 3MF
│   └── Filament_Card_白橡木.3mf             # Pre-generated sample 3MF
└── template/
    └── card_template.3mf                   # Backup reference template
```

---

## 🏗️ 4. Technical Architecture (核心技术实现)

### 4.1 Dual-Engine 3MF Generation
The project maintains two parallel implementations of the watertight 3MF generator:
1. **Client-Side Engine (`index.html` / `zh.html`)**:
   - **Contour Tracing**: Custom 2D Marching Squares implementation with sub-pixel linear interpolation to trace vector contours from high-resolution canvas text rasterization.
   - **Polygon Triangulation**: Mapbox [Earcut](https://github.com/mapbox/earcut) for fast, robust tessellation of polygons with complex holes (e.g., `O`, `P`, `B`, `A`, and Chinese characters like `品`, `回`, `国`).
   - **3MF Packaging**: [JSZip](https://stuk.github.io/jszip/) extracts `card_template.3mf`, dynamically injects XML meshes into `3D/Objects/object_18.model`, updates component matrices in `3D/3dmodel.model` and `Metadata/model_settings.config`, updates colors in `Metadata/project_settings.config`, and outputs a ready-to-print `.3mf` blob.
2. **Python CLI Engine (`make_filament_card.py`)**:
   - Uses `Pillow` and `opencv-python` for font rendering and boundary extraction.
   - Custom triangle ear-clipping and side-wall quad generation to assemble manifold 3D meshes.
   - Exact coordinate alignment matching the JS engine.

### 4.2 Slicer Calibration & 0.1 mm Layer Height
- The card features:
  - 5-step light transmission stairs: **`0.8 mm`**, **`0.6 mm`**, **`0.4 mm`**, **`0.2 mm`**, **`0.1 mm`**.
  - Recessed pocket floor at `Z = 0.5 mm`, card top surface at `Z = 1.0 mm`.
  - Default text inlay relief: **`0.5 mm`** (from `Z = 0.5 mm` to `Z = 1.0 mm`, perfectly flush).
- **Why 0.1 mm layer height is required**:
  - The smallest step (`0.1 mm`) is exactly **1 layer**.
  - The other steps (`0.2, 0.4, 0.6, 0.8 mm`) are exactly **2, 4, 6, 8 layers**.
  - The flush inlay (`0.5 mm`) is exactly **5 layers**.
  - Both `Metadata/project_settings.config` and `Metadata/plate_1.json` are pre-calibrated to `layer_height: "0.1"` and `initial_layer_print_height: "0.1"`.

### 4.3 Bambu Studio Multi-Part Model Structure
In the generated 3MF:
- `object_id = 2` ("sample card (short)"): Base card body (Filament 1).
- `object_id = 3`: Inlay text mesh (Filament 2).
- `object_id = 4`: Circular color swatch cylinder (Filament 3, matching Filament 1).
- Because `Filament 1` and `Filament 3` share the exact same sample filament material and color, users only need **2 AMS slots** (or 2 physical filaments) to print the card.

---

## 🧪 5. Development & Testing Workflow (本地调试与验证)

### Run Local Dev Server:
```bash
# Install dependencies
pip install -r requirements.txt

# Start dev server on http://localhost:8088
python3 app.py
```

### CLI Generation Test:
```bash
# Test English card generation with White text
python3 make_filament_card.py "PLA WOOD" "White Oak" "(13106)" "#D6CCA3" 0.5 --text-hex "#FFFFFF" --preview

# Test Chinese card generation
python3 make_filament_card.py "PLA WOOD" "白橡木" "(13106)" "#D6CCA3" 0.5 --text-hex "#FFFFFF" --preview
```

### Store URL Extractor:
```bash
# Scrape variants from a Bambu Lab store URL
python3 extractor.py "https://us.store.bambulab.com/products/pla-wood"
```
