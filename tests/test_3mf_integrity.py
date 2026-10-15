#!/usr/bin/env python3
"""
Automated 3MF Package & XML Integrity Test Suite
Verifies:
1. JavaScript client-side 3MF XML generation in index.html and zh.html
2. Python CLI generation output
3. XML syntax, mesh integrity, and 3-color filament standard
"""

import os
import re
import sys
import json
import zipfile
import tempfile
import xml.etree.ElementTree as ET

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)


def test_js_xml_builder(html_filename):
    """Verify that buildObject18Xml in HTML produces well-formed, valid XML with both objects."""
    filepath = os.path.join(REPO_ROOT, html_filename)
    assert os.path.exists(filepath), f"File {html_filename} not found"

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Extract buildObject18Xml JS function body
    match = re.search(r"function buildObject18Xml\([^)]*\)\s*\{([\s\S]*?)\n    \}", content)
    assert match, f"Could not find buildObject18Xml in {html_filename}"

    fn_body = match.group(1)
    assert '<object id="3"' in fn_body, f"Missing object 3 in {html_filename}"
    assert '<object id="4"' in fn_body, f"Missing object 4 in {html_filename}"
    assert fn_body.count("</vertices>") >= 2, f"Missing </vertices> in {html_filename}"
    assert fn_body.count("<triangles>") >= 2, f"Missing <triangles> in {html_filename}"
    assert fn_body.count("</triangles>") >= 2, f"Missing </triangles> in {html_filename}"
    assert "swatchTris" in fn_body and "swatchVerts" in fn_body, f"Missing swatch loops in {html_filename}"

    # If Node.js is available, directly execute the JS function and parse with Python XML parser
    import shutil
    import subprocess
    if shutil.which("node"):
        js_code = f"""
        const fs = require('fs');
        const content = fs.readFileSync('{filepath}', 'utf8');
        const match = content.match(/function buildObject18Xml[\\s\\S]*?^    \\}}/m);
        eval(match[0]);
        const xml = buildObject18Xml(
            [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
            [[0, 1, 2]],
            [[5, 5, 0], [6, 5, 0], [5, 6, 0]],
            [[0, 1, 2]]
        );
        process.stdout.write(xml);
        """
        res = subprocess.run(["node", "-e", js_code], capture_output=True, text=True, check=True)
        xml_out = res.stdout
        try:
            root = ET.fromstring(xml_out)
        except ET.ParseError as e:
            raise AssertionError(f"XML parse error in {html_filename} generated XML: {e}")

        ns = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
        objs = root.findall(".//m:object", ns)
        assert len(objs) == 2, f"Expected 2 objects in {html_filename}, found {len(objs)}"
        for obj in objs:
            verts = obj.findall(".//m:vertex", ns)
            tris = obj.findall(".//m:triangle", ns)
            assert len(verts) > 0, f"Object {obj.attrib.get('id')} has no vertices"
            assert len(tris) > 0, f"Object {obj.attrib.get('id')} has no triangles"


def validate_3mf_package(path_or_bytes):
    """Deep inspect a .3mf file for zip, XML, JSON, and mesh consistency."""
    if isinstance(path_or_bytes, (str, os.PathLike)):
        z = zipfile.ZipFile(path_or_bytes)
    else:
        import io
        z = zipfile.ZipFile(io.BytesIO(path_or_bytes))

    errors = []
    namelist = z.namelist()

    # 1. Essential files
    required = [
        "3D/3dmodel.model",
        "3D/Objects/object_2.model",
        "3D/Objects/object_18.model",
        "Metadata/model_settings.config",
        "Metadata/project_settings.config"
    ]
    for req in required:
        if req not in namelist:
            errors.append(f"Missing required 3MF entry: {req}")

    # 2. Validate all XML files
    xml_files = [n for n in namelist if n.endswith(".model") or n.endswith(".xml") or n in ["Metadata/model_settings.config", "Metadata/slice_info.config"]]
    for name in xml_files:
        try:
            root = ET.fromstring(z.read(name))
        except ET.ParseError as e:
            errors.append(f"XML ParseError in {name}: {e}")
            continue

        if name == "3D/Objects/object_18.model":
            ns = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
            objs = root.findall(".//m:object", ns)
            obj_map = {o.attrib.get("id"): o for o in objs}
            for oid, label in [("3", "Text Info"), ("4", "Color Swatch")]:
                if oid not in obj_map:
                    errors.append(f"Missing object id={oid} ({label}) in object_18.model")
                else:
                    verts = obj_map[oid].findall(".//m:vertex", ns)
                    tris = obj_map[oid].findall(".//m:triangle", ns)
                    if len(verts) < 3:
                        errors.append(f"Object {oid} ({label}) has {len(verts)} vertices (< 3)")
                    if len(tris) < 1:
                        errors.append(f"Object {oid} ({label}) has {len(tris)} triangles (< 1)")

    # 3. Validate project_settings JSON & 3-color standard
    if "Metadata/project_settings.config" in namelist:
        try:
            cfg = json.loads(z.read("Metadata/project_settings.config"))
            cols = cfg.get("filament_colour", [])
            if len(cols) < 3:
                errors.append(f"filament_colour must have at least 3 slots, found {len(cols)}")
            for idx, c in enumerate(cols[:3]):
                if not re.fullmatch(r"#[0-9A-Fa-f]{6}", c):
                    errors.append(f"Invalid HEX format for filament {idx+1}: {c}")
        except Exception as e:
            errors.append(f"JSON ParseError in project_settings.config: {e}")

    return errors


def test_python_generator():
    """Verify that make_filament_card.py generates a valid 3MF."""
    import make_filament_card as mfc
    with tempfile.NamedTemporaryFile(suffix=".3mf", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        mfc.generate_card(
            material="PLA Basic",
            color="Automated Test",
            code="(99999)",
            hex_color="#10B981",
            relief=0.5,
            out_path=tmp_path,
            swatch_d=7.0,
            thicken=False,
            preview=False,
            base_hex="#10B981",
            text_hex="#FFFFFF"
        )
        errors = validate_3mf_package(tmp_path)
        assert not errors, f"Python generator 3MF validation failed: {errors}"
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def test_example_files():
    """Verify all pre-generated examples in examples/ are valid."""
    examples_dir = os.path.join(REPO_ROOT, "examples")
    if not os.path.isdir(examples_dir):
        return
    for f in os.listdir(examples_dir):
        if f.endswith(".3mf"):
            path = os.path.join(examples_dir, f)
            errors = validate_3mf_package(path)
            assert not errors, f"Example file {f} failed validation: {errors}"


def main():
    print("Running automated 3MF integrity tests...")
    failures = []

    print("1. Checking index.html JS XML builder...", end=" ", flush=True)
    try:
        test_js_xml_builder("index.html")
        print("PASSED")
    except Exception as e:
        print("FAILED")
        failures.append(f"index.html: {e}")

    print("2. Checking zh.html JS XML builder...", end=" ", flush=True)
    try:
        test_js_xml_builder("zh.html")
        print("PASSED")
    except Exception as e:
        print("FAILED")
        failures.append(f"zh.html: {e}")

    print("3. Checking Python CLI 3MF generator...", end=" ", flush=True)
    try:
        test_python_generator()
        print("PASSED")
    except Exception as e:
        import traceback
        print("FAILED")
        traceback.print_exc()
        failures.append(f"Python generator: {e}")

    print("4. Checking pre-generated examples in examples/...", end=" ", flush=True)
    try:
        test_example_files()
        print("PASSED")
    except Exception as e:
        print("FAILED")
        failures.append(f"Examples validation: {e}")

    if failures:
        print(f"\n❌ {len(failures)} test(s) failed:")
        for f in failures:
            print("  •", f)
        sys.exit(1)

    print("\n✅ All 3MF integrity tests passed successfully!")


if __name__ == "__main__":
    main()
