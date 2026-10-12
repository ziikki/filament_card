#!/usr/bin/env python3
"""
Bambu Lab Filament Card Studio - Web Server
Runs a local web application to extract filament details, preview the card, and generate .3MF files.
"""
import base64
import json
import os
import re
import tempfile
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

import cv2
import make_filament_card as mfc
import extractor

PORT = 8088
HERE = os.path.dirname(os.path.abspath(__file__))

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Bambu Lab 耗材样本卡生成器 | Filament Card Studio</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #0f1117;
      --card-bg: #181b24;
      --card-border: #262a36;
      --text-main: #f3f4f6;
      --text-muted: #9ca3af;
      --bambu-green: #00ae42;
      --bambu-green-hover: #009337;
      --accent: #3b82f6;
      --accent-hover: #2563eb;
      --input-bg: #11131a;
      --input-border: #2e3444;
      --focus-ring: rgba(0, 174, 66, 0.35);
      --badge-bg: #222734;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background-color: var(--bg);
      color: var(--text-main);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }

    header {
      background-color: rgba(24, 27, 36, 0.85);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--card-border);
      padding: 1rem 2rem;
      position: sticky;
      top: 0;
      z-index: 50;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }

    .brand-icon {
      width: 32px;
      height: 32px;
      background: linear-gradient(135deg, #00ae42, #10b981);
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      color: #fff;
      font-weight: 700;
      font-size: 1.1rem;
      box-shadow: 0 4px 12px rgba(0, 174, 66, 0.3);
    }

    .brand-title {
      font-size: 1.15rem;
      font-weight: 700;
      letter-spacing: -0.01em;
    }

    .brand-subtitle {
      font-size: 0.8rem;
      color: var(--text-muted);
    }

    .header-links {
      display: flex;
      gap: 1rem;
      font-size: 0.85rem;
    }

    .badge {
      background-color: var(--badge-bg);
      color: #10b981;
      padding: 0.25rem 0.6rem;
      border-radius: 9999px;
      font-size: 0.75rem;
      font-weight: 600;
      border: 1px solid rgba(16, 185, 129, 0.2);
    }

    main {
      flex: 1;
      max-width: 1300px;
      width: 100%;
      margin: 0 auto;
      padding: 2rem;
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 2rem;
    }

    @media (max-width: 960px) {
      main { grid-template-columns: 1fr; }
    }

    .panel {
      background-color: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 1.5rem;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3);
    }

    .panel-title {
      font-size: 1.05rem;
      font-weight: 600;
      margin-bottom: 1rem;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }

    .section-box {
      margin-bottom: 1.5rem;
    }

    label {
      display: block;
      font-size: 0.85rem;
      font-weight: 500;
      color: var(--text-muted);
      margin-bottom: 0.4rem;
    }

    .input-group {
      display: flex;
      gap: 0.5rem;
    }

    input[type="text"], input[type="number"], select {
      width: 100%;
      background-color: var(--input-bg);
      border: 1px solid var(--input-border);
      color: var(--text-main);
      padding: 0.65rem 0.85rem;
      border-radius: 8px;
      font-size: 0.9rem;
      outline: none;
      transition: all 0.2s;
    }

    input:focus, select:focus {
      border-color: var(--bambu-green);
      box-shadow: 0 0 0 3px var(--focus-ring);
    }

    button {
      cursor: pointer;
      font-family: inherit;
      font-weight: 600;
      border-radius: 8px;
      transition: all 0.2s;
      border: none;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 0.5rem;
      padding: 0.65rem 1.2rem;
      font-size: 0.9rem;
    }

    .btn-primary {
      background-color: var(--bambu-green);
      color: #fff;
      box-shadow: 0 4px 14px rgba(0, 174, 66, 0.35);
    }

    .btn-primary:hover {
      background-color: var(--bambu-green-hover);
      transform: translateY(-1px);
    }

    .btn-secondary {
      background-color: var(--badge-bg);
      color: var(--text-main);
      border: 1px solid var(--card-border);
    }

    .btn-secondary:hover {
      background-color: #2b3242;
    }

    .btn-small {
      padding: 0.35rem 0.65rem;
      font-size: 0.8rem;
    }

    .quick-tags {
      display: flex;
      flex-wrap: wrap;
      gap: 0.4rem;
      margin-top: 0.6rem;
    }

    .tag-btn {
      background: #11131a;
      border: 1px solid var(--input-border);
      color: var(--text-muted);
      font-size: 0.75rem;
      padding: 0.25rem 0.5rem;
      border-radius: 6px;
      cursor: pointer;
    }

    .tag-btn:hover {
      color: var(--text-main);
      border-color: var(--accent);
    }

    /* Swatches bar */
    .variants-container {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      margin-top: 0.5rem;
      max-height: 180px;
      overflow-y: auto;
      padding: 0.5rem;
      background: var(--input-bg);
      border-radius: 8px;
      border: 1px solid var(--input-border);
    }

    .variant-chip {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      padding: 0.3rem 0.6rem;
      border-radius: 9999px;
      font-size: 0.8rem;
      cursor: pointer;
      transition: all 0.15s;
    }

    .variant-chip:hover {
      border-color: var(--bambu-green);
      transform: translateY(-1px);
    }

    .variant-chip.active {
      border-color: var(--bambu-green);
      background: rgba(0, 174, 66, 0.15);
      color: #fff;
    }

    .color-dot {
      width: 14px;
      height: 14px;
      border-radius: 50%;
      border: 1px solid rgba(255, 255, 255, 0.2);
      flex-shrink: 0;
    }

    /* Grid for form inputs */
    .grid-2 {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1rem;
      margin-bottom: 1rem;
    }

    .color-input-wrapper {
      display: flex;
      gap: 0.5rem;
      align-items: center;
    }

    input[type="color"] {
      -webkit-appearance: none;
      border: none;
      width: 42px;
      height: 38px;
      border-radius: 8px;
      cursor: pointer;
      background: none;
    }

    input[type="color"]::-webkit-color-swatch-wrapper {
      padding: 0;
    }

    input[type="color"]::-webkit-color-swatch {
      border: 1px solid var(--input-border);
      border-radius: 8px;
    }

    /* Preview panel */
    .preview-container {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      background: #0d0f14;
      border-radius: 12px;
      padding: 1.5rem;
      border: 1px solid var(--input-border);
      position: relative;
      min-height: 320px;
    }

    .preview-card-img {
      max-width: 100%;
      height: auto;
      border-radius: 10px;
      box-shadow: 0 15px 35px -5px rgba(0, 0, 0, 0.6);
      transition: opacity 0.2s;
    }

    .preview-card-img.loading {
      opacity: 0.4;
    }

    .spinner {
      position: absolute;
      width: 36px;
      height: 36px;
      border: 3px solid rgba(255,255,255,0.1);
      border-top-color: var(--bambu-green);
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
      display: none;
    }

    .spinner.visible {
      display: block;
    }

    @keyframes spin {
      to { transform: rotate(360deg); }
    }

    .specs-list {
      margin-top: 1.5rem;
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 0.75rem;
      width: 100%;
    }

    .spec-card {
      background: var(--input-bg);
      border: 1px solid var(--input-border);
      border-radius: 8px;
      padding: 0.6rem 0.8rem;
      text-align: center;
    }

    .spec-val {
      font-size: 0.95rem;
      font-weight: 700;
      color: var(--text-main);
    }

    .spec-lbl {
      font-size: 0.7rem;
      color: var(--text-muted);
      margin-top: 0.15rem;
    }

    .download-section {
      margin-top: 1.5rem;
      display: flex;
      gap: 1rem;
    }

    .download-section button {
      flex: 1;
      padding: 0.9rem;
      font-size: 1rem;
    }

    .toast {
      position: fixed;
      bottom: 2rem;
      right: 2rem;
      background: #1f2937;
      color: #fff;
      padding: 0.75rem 1.25rem;
      border-radius: 8px;
      box-shadow: 0 10px 25px rgba(0,0,0,0.5);
      border-left: 4px solid var(--bambu-green);
      font-size: 0.9rem;
      z-index: 100;
      opacity: 0;
      transform: translateY(10px);
      transition: all 0.3s;
      pointer-events: none;
    }

    .toast.show {
      opacity: 1;
      transform: translateY(0);
    }

    .cli-box {
      margin-top: 1rem;
      background: #0d0f14;
      border: 1px solid var(--input-border);
      border-radius: 8px;
      padding: 0.6rem 0.8rem;
      font-family: monospace;
      font-size: 0.75rem;
      color: #93c5fd;
      display: flex;
      justify-content: space-between;
      align-items: center;
      overflow-x: auto;
    }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <div class="brand-icon">B</div>
      <div>
        <div class="brand-title">Bambu Lab Filament Card Studio</div>
        <div class="brand-subtitle">耗材样本卡生成器 & 3MF 导出工具</div>
      </div>
    </div>
    <div class="header-links">
      <span class="badge">● Prime Tower Ready</span>
      <span class="badge">● 0.4mm Nozzle Optimized</span>
    </div>
  </header>

  <main>
    <!-- Left panel: URL extractor and card settings -->
    <div class="panel">
      <!-- 1. URL Extractor -->
      <div class="section-box">
        <label for="bambuUrl">1. 粘贴 Bambu Lab 商城链接 (自动解析)</label>
        <div class="input-group">
          <input type="text" id="bambuUrl" placeholder="https://us.store.bambulab.com/products/pla-wood?id=43075832086664" />
          <button id="extractBtn" class="btn-primary">
            <span id="extractSpinner" style="display:none;">⏳</span>
            <span>解析网页</span>
          </button>
        </div>
        <div class="quick-tags">
          <span style="font-size:0.75rem; color:var(--text-muted); align-self:center;">快速填充:</span>
          <button class="tag-btn" onclick="loadPreset('pla-wood')">PLA Wood (White Oak 13106)</button>
          <button class="tag-btn" onclick="loadPreset('pla-matte-gold')">PLA Matte (Iridium Gold 13008)</button>
          <button class="tag-btn" onclick="loadPreset('petg-hf-black')">PETG HF (Black 30101)</button>
        </div>
      </div>

      <!-- 2. Local database search -->
      <div class="section-box">
        <label for="dbSearch">或直接搜索 Bambu 官方耗材库 (314种颜色)</label>
        <div class="input-group">
          <input type="text" id="dbSearch" placeholder="输入编号如 13106 或颜色名如 White Oak, 白橡木, 黑胡桃..." oninput="filterDatabase()" />
        </div>
      </div>

      <!-- 3. Variants list (chips) -->
      <div class="section-box" id="variantsBox" style="display: none;">
        <label id="variantsLabel">检测到的颜色变体 (点击快速切换):</label>
        <div class="variants-container" id="variantsContainer"></div>
      </div>

      <hr style="border:0; border-top:1px solid var(--card-border); margin: 1.5rem 0;" />

      <!-- 4. Card text details -->
      <div class="panel-title">
        <span>样本卡文字与参数配置</span>
        <button class="btn-secondary btn-small" onclick="toggleLanguage()">
          <span id="langToggleText">切换为中文 (白橡木)</span>
        </button>
      </div>

      <div class="grid-2">
        <div>
          <label for="matInput">材料类型 (第1行)</label>
          <input type="text" id="matInput" value="PLA WOOD" oninput="triggerPreviewDebounced()" />
        </div>
        <div>
          <label for="colorInput">颜色名称 (第2行)</label>
          <input type="text" id="colorInput" value="White Oak" oninput="triggerPreviewDebounced()" />
        </div>
      </div>

      <div class="grid-2">
        <div>
          <label for="codeInput">编号 (第3行左侧)</label>
          <input type="text" id="codeInput" value="(13106)" oninput="triggerPreviewDebounced()" />
        </div>
        <div>
          <label for="hexInput">HEX 色号 (第3行右侧与色块)</label>
          <div class="color-input-wrapper">
            <input type="color" id="colorPicker" value="#D6CCA3" oninput="onColorPickerChange(this.value)" />
            <input type="text" id="hexInput" value="#D6CCA3" oninput="onHexInputChange(this.value)" />
          </div>
        </div>
      </div>

      <div class="grid-2">
        <div>
          <label for="reliefInput">浮雕高度 (Relief, 默认 1.2 mm; 0.5 齐平)</label>
          <input type="number" id="reliefInput" value="1.2" step="0.1" min="0.5" max="3.0" oninput="triggerPreviewDebounced()" />
        </div>
        <div>
          <label for="swatchDia">色块直径 (Swatch, 默认 7.0 mm)</label>
          <input type="number" id="swatchDia" value="7.0" step="0.5" min="4.0" max="10.0" oninput="triggerPreviewDebounced()" />
        </div>
      </div>

      <div style="display: flex; align-items: center; gap: 0.5rem; margin-top: 0.5rem;">
        <input type="checkbox" id="thickenCheck" onchange="triggerPreviewDebounced()" />
        <label for="thickenCheck" style="margin-bottom:0; cursor:pointer;">
          形态学加粗细笔画 (仅针对粗喷嘴或极细非 Arachne 切片)
        </label>
      </div>
    </div>

    <!-- Right panel: Live Preview & 3MF Generation -->
    <div class="panel" style="display:flex; flex-direction:column;">
      <div class="panel-title">
        <span>实时渲染预览 (Exact Pocket Layout)</span>
        <span class="badge" id="strokeBadge">笔画: 0.36 mm</span>
      </div>

      <div class="preview-container">
        <div class="spinner" id="previewSpinner"></div>
        <img id="previewImg" class="preview-card-img" alt="Card Preview" src="" />
      </div>

      <div class="specs-list">
        <div class="spec-card">
          <div class="spec-val">40.4 × 30.4</div>
          <div class="spec-lbl">凹槽尺寸 (mm)</div>
        </div>
        <div class="spec-card">
          <div class="spec-val" id="specTopZ">2.70 mm</div>
          <div class="spec-lbl">浮雕顶面 Z</div>
        </div>
        <div class="spec-card">
          <div class="spec-val" style="color:#10b981;">100% 封闭</div>
          <div class="spec-lbl">Watertight Mesh</div>
        </div>
      </div>

      <div class="download-section">
        <button id="downloadBtn" class="btn-primary" onclick="generateAndDownload()">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
          <span>生成并下载 .3MF 文件</span>
        </button>
      </div>

      <div class="cli-box" id="cliBox">
        <span id="cliText">python3 make_filament_card.py "PLA WOOD" "White Oak" "(13106)" "#D6CCA3" 1.2</span>
        <button class="btn-secondary btn-small" onclick="copyCli()" style="padding:0.2rem 0.5rem; font-size:0.7rem;">复制命令</button>
      </div>
    </div>
  </main>

  <div class="toast" id="toast">提示信息</div>

  <script>
    let filamentDb = [];
    let currentZhName = "白橡木";
    let currentEnName = "White Oak";
    let isZh = false;
    let debounceTimer = null;

    // Initialize
    window.addEventListener('DOMContentLoaded', async () => {
      await loadDatabase();
      // Auto trigger first preview
      updatePreview();
    });

    async function loadDatabase() {
      try {
        const resp = await fetch('/api/database');
        filamentDb = await resp.json();
      } catch (e) {
        console.error('Failed to load DB:', e);
      }
    }

    function showToast(msg) {
      const t = document.getElementById('toast');
      t.textContent = msg;
      t.classList.add('show');
      setTimeout(() => t.classList.remove('show'), 3000);
    }

    function onColorPickerChange(val) {
      document.getElementById('hexInput').value = val.toUpperCase();
      triggerPreviewDebounced();
    }

    function onHexInputChange(val) {
      let h = val.trim();
      if (!h.startsWith('#')) h = '#' + h;
      if (/^#[0-9A-Fa-f]{6}$/.test(h)) {
        document.getElementById('colorPicker').value = h;
      }
      triggerPreviewDebounced();
    }

    function triggerPreviewDebounced() {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(updatePreview, 250);
      updateCliBox();
    }

    function updateCliBox() {
      const mat = document.getElementById('matInput').value;
      const col = document.getElementById('colorInput').value;
      const code = document.getElementById('codeInput').value;
      const hex = document.getElementById('hexInput').value;
      const relief = document.getElementById('reliefInput').value;
      const thicken = document.getElementById('thickenCheck').checked;
      let cmd = `python3 make_filament_card.py "${mat}" "${col}" "${code}" "${hex}" ${relief}`;
      if (thicken) cmd += " --thicken";
      document.getElementById('cliText').textContent = cmd;
    }

    function copyCli() {
      navigator.clipboard.writeText(document.getElementById('cliText').textContent);
      showToast('已复制 CLI 执行命令到剪贴板！');
    }

    async function updatePreview() {
      const mat = document.getElementById('matInput').value;
      const col = document.getElementById('colorInput').value;
      const code = document.getElementById('codeInput').value;
      let hex = document.getElementById('hexInput').value.trim();
      if (!hex.startsWith('#')) hex = '#' + hex;
      const relief = parseFloat(document.getElementById('reliefInput').value) || 1.2;
      const swatchD = parseFloat(document.getElementById('swatchDia').value) || 7.0;
      const thicken = document.getElementById('thickenCheck').checked;

      const img = document.getElementById('previewImg');
      const spinner = document.getElementById('previewSpinner');
      spinner.classList.add('visible');
      img.classList.add('loading');

      try {
        const resp = await fetch('/api/preview', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            material: mat,
            color: col,
            code: code,
            hex: hex,
            swatch_d: swatchD,
            relief: relief,
            thicken: thicken
          })
        });
        const data = await resp.json();
        if (data.success) {
          img.src = data.preview_base64;
          if (data.stroke_info && data.stroke_info.before) {
            document.getElementById('strokeBadge').textContent = `最细笔画: ${data.stroke_info.before.toFixed(2)} mm`;
          }
          document.getElementById('specTopZ').textContent = `${(relief + 1.5).toFixed(2)} mm`;
        } else {
          showToast('预览生成失败: ' + (data.error || '未知错误'));
        }
      } catch (err) {
        console.error(err);
      } finally {
        spinner.classList.remove('visible');
        img.classList.remove('loading');
      }
    }

    // Toggle English <-> Chinese
    function toggleLanguage() {
      isZh = !isZh;
      const colInput = document.getElementById('colorInput');
      if (isZh) {
        colInput.value = currentZhName || colInput.value;
        document.getElementById('langToggleText').textContent = `切换为英文 (${currentEnName})`;
      } else {
        colInput.value = currentEnName || colInput.value;
        document.getElementById('langToggleText').textContent = `切换为中文 (${currentZhName})`;
      }
      triggerPreviewDebounced();
    }

    // Extract URL
    document.getElementById('extractBtn').addEventListener('click', async () => {
      const url = document.getElementById('bambuUrl').value.trim();
      if (!url) {
        showToast('请先输入 Bambu Lab 商城网页链接');
        return;
      }

      const btn = document.getElementById('extractBtn');
      const spinner = document.getElementById('extractSpinner');
      btn.disabled = true;
      spinner.style.display = 'inline';

      try {
        const resp = await fetch('/api/extract', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: url })
        });
        const data = await resp.json();

        if (data.success && data.variants && data.variants.length > 0) {
          renderVariants(data.variants, data.selected_index || 0);
          showToast(`成功解析 ${data.variants.length} 个颜色变体！`);
        } else {
          showToast('未能从该页面提取到耗材变体，请检查链接或手动选择。');
        }
      } catch (err) {
        showToast('请求出错: ' + err.message);
      } finally {
        btn.disabled = false;
        spinner.style.display = 'none';
      }
    });

    function renderVariants(variants, selectIdx) {
      const box = document.getElementById('variantsBox');
      const container = document.getElementById('variantsContainer');
      container.innerHTML = '';
      box.style.display = 'block';

      variants.forEach((v, idx) => {
        const chip = document.createElement('div');
        chip.className = 'variant-chip' + (idx === selectIdx ? ' active' : '');
        chip.innerHTML = `
          <span class="color-dot" style="background-color: ${v.hex};"></span>
          <span>${v.name_en || v.name}</span>
          <span style="opacity:0.6; font-size:0.75rem;">${v.code}</span>
        `;
        chip.onclick = () => selectVariant(v, chip);
        container.appendChild(chip);
      });

      if (variants[selectIdx]) {
        selectVariant(variants[selectIdx], container.children[selectIdx]);
      }
    }

    function selectVariant(v, chipElem) {
      document.querySelectorAll('.variant-chip').forEach(c => c.classList.remove('active'));
      if (chipElem) chipElem.classList.add('active');

      currentEnName = v.name_en || v.name;
      currentZhName = v.name_zh || v.name;
      isZh = false;

      document.getElementById('matInput').value = v.material || 'PLA';
      document.getElementById('colorInput').value = currentEnName;
      document.getElementById('codeInput').value = v.code.startsWith('(') ? v.code : `(${v.code})`;
      document.getElementById('hexInput').value = v.hex;
      document.getElementById('colorPicker').value = v.hex;
      document.getElementById('langToggleText').textContent = `切换为中文 (${currentZhName})`;

      triggerPreviewDebounced();
    }

    // Presets
    function loadPreset(key) {
      if (key === 'pla-wood') {
        document.getElementById('bambuUrl').value = 'https://us.store.bambulab.com/products/pla-wood?id=43075832086664';
        document.getElementById('extractBtn').click();
      } else if (key === 'pla-matte-gold') {
        selectVariant({
          material: 'PLA MATTE',
          name: 'Iridium Gold',
          name_en: 'Iridium Gold',
          name_zh: '铱金',
          code: '(13008)',
          hex: '#A2D312'
        }, null);
      } else if (key === 'petg-hf-black') {
        selectVariant({
          material: 'PETG HF',
          name: 'Black',
          name_en: 'Black',
          name_zh: '黑色',
          code: '(30101)',
          hex: '#000000'
        }, null);
      }
    }

    // Search Database
    function filterDatabase() {
      const q = document.getElementById('dbSearch').value.trim().toLowerCase();
      if (!q || !filamentDb.length) return;

      const matches = filamentDb.filter(item => {
        return item.code.includes(q) ||
               item.name_en.toLowerCase().includes(q) ||
               item.name_zh.includes(q) ||
               item.material.toLowerCase().includes(q);
      }).slice(0, 15);

      if (matches.length > 0) {
        renderVariants(matches.map(m => ({
          material: m.material.toUpperCase(),
          name: m.name_en,
          name_en: m.name_en,
          name_zh: m.name_zh,
          code: `(${m.code})`,
          hex: m.hex
        })), 0);
      }
    }

    // Generate & Download 3MF
    async function generateAndDownload() {
      const mat = document.getElementById('matInput').value;
      const col = document.getElementById('colorInput').value;
      const code = document.getElementById('codeInput').value;
      let hex = document.getElementById('hexInput').value.trim();
      if (!hex.startsWith('#')) hex = '#' + hex;
      const relief = parseFloat(document.getElementById('reliefInput').value) || 1.2;
      const swatchD = parseFloat(document.getElementById('swatchDia').value) || 7.0;
      const thicken = document.getElementById('thickenCheck').checked;

      const btn = document.getElementById('downloadBtn');
      const origText = btn.innerHTML;
      btn.disabled = true;
      btn.innerHTML = '<span>⚡ 正在生成 3MF 模型...</span>';

      try {
        const resp = await fetch('/api/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            material: mat,
            color: col,
            code: code,
            hex: hex,
            relief: relief,
            swatch_d: swatchD,
            thicken: thicken
          })
        });

        if (!resp.ok) {
          const err = await resp.json();
          throw new Error(err.error || '生成失败');
        }

        const blob = await resp.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        const cleanCol = col.replace(/[/\\\\?%*:|"<> ]/g, '_');
        a.download = `耗材样本卡_${cleanCol}.3mf`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        showToast(`🎉 3MF 样本卡已生成并开始下载！`);
      } catch (e) {
        showToast('生成失败: ' + e.message);
      } finally {
        btn.disabled = false;
        btn.innerHTML = origText;
      }
    }
  </script>
</body>
</html>
"""

class ThreadingSimpleServer(ThreadingMixIn, HTTPServer):
    pass

class FilamentStudioHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Concise logging
        print(f"[{self.command}] {self.path} - {args[0]}")

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            idx_file = os.path.join(HERE, "index.html")
            if os.path.exists(idx_file):
                with open(idx_file, "rb") as f:
                    content = f.read()
            else:
                content = HTML_TEMPLATE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        elif path in ["/filament_db.json", "/api/database"]:
            db_path = os.path.join(HERE, "filament_db.json")
            if os.path.exists(db_path):
                with open(db_path, "rb") as f:
                    content = f.read()
            else:
                content = b"[]"
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        elif path in ["/card_template.3mf", "/template/card_template.3mf"]:
            tmpl_path = os.path.join(HERE, "card_template.3mf")
            if not os.path.exists(tmpl_path):
                tmpl_path = os.path.join(HERE, "template", "card_template.3mf")
            if os.path.exists(tmpl_path):
                with open(tmpl_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.ms-package.3dmanufacturing-3dmodel+xml")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            else:
                self.send_response(404)
                self.end_headers()
                return

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"

        try:
            body = json.loads(post_data)
        except Exception:
            body = {}

        if path == "/api/extract":
            url = body.get("url", "")
            res = extractor.extract_from_url(url)
            self.send_response(200 if res.get("success") else 400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))
            return

        elif path == "/api/preview":
            material = body.get("material", "PLA WOOD")
            color = body.get("color", "White Oak")
            code = body.get("code", "(13106)")
            hex_color = body.get("hex", "#D6CCA3")
            swatch_d = float(body.get("swatch_d", 7.0))
            thicken = bool(body.get("thicken", False))

            try:
                bgr_img, warns, stroke_info = mfc.render_preview_image(
                    material=material,
                    color=color,
                    code=code,
                    hex_color=hex_color,
                    swatch_d=swatch_d,
                    thicken=thicken
                )
                ret, buf = cv2.imencode(".png", bgr_img)
                b64 = base64.b64encode(buf).decode("ascii")
                data_uri = f"data:image/png;base64,{b64}"

                resp = {
                    "success": True,
                    "preview_base64": data_uri,
                    "warnings": warns,
                    "stroke_info": stroke_info
                }
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(resp, ensure_ascii=False).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
            return

        elif path == "/api/generate":
            material = body.get("material", "PLA WOOD")
            color = body.get("color", "White Oak")
            code = body.get("code", "(13106)")
            hex_color = body.get("hex", "#D6CCA3")
            relief = float(body.get("relief", 1.2))
            swatch_d = float(body.get("swatch_d", 7.0))
            thicken = bool(body.get("thicken", False))

            try:
                with tempfile.NamedTemporaryFile(suffix=".3mf", delete=False) as tmp:
                    tmp_out = tmp.name

                meta = mfc.generate_card(
                    material=material,
                    color=color,
                    code=code,
                    hex_color=hex_color,
                    relief=relief,
                    out_path=tmp_out,
                    swatch_d=swatch_d,
                    thicken=thicken,
                    preview=False
                )

                with open(tmp_out, "rb") as f:
                    file_bytes = f.read()

                try:
                    os.unlink(tmp_out)
                except Exception:
                    pass

                clean_col = re.sub(r'[\\/:*?"<>|\s]+', '_', color).strip('_')
                filename = f"耗材样本卡_{clean_col}.3mf"
                # UTF-8 encoded filename in RFC 5987 format
                quoted_fn = urllib.parse.quote(filename)

                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.ms-package.3dmanufacturing-3dmodel+xml")
                self.send_header("Content-Disposition", f'attachment; filename="{quoted_fn}"; filename*=UTF-8\'\'{quoted_fn}')
                self.send_header("Content-Length", str(len(file_bytes)))
                self.end_headers()
                self.wfile.write(file_bytes)
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))
            return

        else:
            self.send_response(404)
            self.end_headers()

def run_server(port=PORT):
    server_address = ('127.0.0.1', port)
    httpd = ThreadingSimpleServer(server_address, FilamentStudioHandler)
    print(f"🚀 Bambu Lab Filament Card Studio running at http://localhost:{port}")
    httpd.serve_forever()

if __name__ == "__main__":
    run_server()
