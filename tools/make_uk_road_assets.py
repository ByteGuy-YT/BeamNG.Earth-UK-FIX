"""Rebuild original UK road paint and circular mph signs (no third-party artwork)."""
import json
import math
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
import dae


def build():
    out = ROOT / "mod/beamng_earth/levels/beamng_earth/art/shapes/beamngEarth/uk_roads"
    out.mkdir(parents=True, exist_ok=True)
    vfs = "/levels/beamng_earth/art/shapes/beamngEarth/uk_roads/"
    paint = Image.new("RGBA", (32, 192), (242, 241, 229, 0))
    ImageDraw.Draw(paint).rectangle((0, 0, 31, 63), fill=(242, 241, 229, 255))
    paint.save(out / "dash.png")
    materials = {}

    def material(name, texture, paint=False):
        d = {"name": name, "mapTo": name, "class": "Material", "version": 1.5,
             "doubleSided": True, "castShadows": not paint,
             "Stages": [{"baseColorMap": vfs + texture, "roughnessFactor": .9, "metallicFactor": 0}, {}, {}, {}]}
        if paint:
            d.update(translucent=True, translucentBlendOp="LerpAlpha", translucentZWrite=False)
        materials[name] = d
    material("uk_line_dashed", "dash.png", True)
    for name, fraction in (("giveway", 2 / 3), ("zebra", .5)):
        paint = Image.new("RGBA", (32, 192), (242, 241, 229, 0))
        ImageDraw.Draw(paint).rectangle((0, 0, 31, int(192 * fraction) - 1), fill=(242, 241, 229, 255))
        paint.save(out / f"{name}.png")
        material(f"uk_line_{name}", f"{name}.png", True)
    font_path = next((p for p in (Path("C:/Windows/Fonts/arialbd.ttf"),
                                 Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")) if p.is_file()), None)
    font = ImageFont.truetype(str(font_path), 132) if font_path else ImageFont.load_default(size=132)
    for limit in (20, 30, 40, 50, 60, 70):
        im = Image.new("RGB", (256, 256), (125, 130, 132))
        draw = ImageDraw.Draw(im)
        draw.ellipse((3, 3, 252, 252), fill=(185, 24, 30))
        draw.ellipse((25, 25, 230, 230), fill=(246, 245, 237))
        draw.text((128, 125), str(limit), font=font, anchor="mm", fill=(18, 20, 21))
        im.save(out / f"speed{limit}.png")
        name = f"uk_speed_{limit}"
        material(name, f"speed{limit}.png")
        # Local +Y is the sign's front, local +X spans its face. Post and back sample a grey texel.
        pos, uv, tri = [], [], []
        for side in (1, -1):
            base = len(pos)
            pos.append((0., side * .018, 2.3)); uv.append((.5, .5) if side > 0 else (.001, .001))
            for j in range(49):
                theta = 2 * math.pi * j / 48
                x, z = math.cos(theta), math.sin(theta)
                pos.append((x * .3, side * .018, 2.3 + z * .3))
                uv.append(((1 - x) / 2, (z + 1) / 2) if side > 0 else (.001, .001))
            for j in range(48):
                t = (base, base + j + 1, base + j + 2)
                tri.append(t if side < 0 else t[::-1])
        # Slim square galvanised post, 2.6 m model height matches Forest scaling.
        for j in range(4):
            theta, theta2 = j * math.pi / 2, (j + 1) * math.pi / 2
            x, y, x2, y2 = .035 * math.cos(theta), .035 * math.sin(theta), .035 * math.cos(theta2), .035 * math.sin(theta2)
            base = len(pos)
            pos.extend([(x, y, 0), (x2, y2, 0), (x2, y2, 2.45), (x, y, 2.45)])
            uv.extend([(.001, .001)] * 4)
            tri.extend([(base, base + 1, base + 2), (base, base + 2, base + 3)])
        dae.write_grid_dae(str(out / f"speed{limit}.dae"), np.array(pos).ravel(), np.array(uv).ravel(),
                           np.array(tri).ravel(), name)
    (out / "main.materials.json").write_text(json.dumps(materials, indent=2) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    print(build())
