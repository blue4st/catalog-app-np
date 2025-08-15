import os
import sys
import argparse
import yaml
import random
from PIL import Image, ImageStat

# === CONFIG ===
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
COLOR_CONFIG_DIR = os.path.join(BASE_DIR, "config", "colors")
STATIC_COLOR_DIR = os.path.join(BASE_DIR, "assets", "colors")
STATIC_SWATCH_DIR = os.path.join(BASE_DIR, "static", "assets", "swatches")
CONTENT_PRODUCTS_DIR = os.path.join(BASE_DIR, "content", "products")

BASE_IMG_DIR = os.path.join(BASE_DIR, "assets", "base")
MASK_IMG_DIR = os.path.join(BASE_DIR, "assets", "mask")
OVERLAY_IMG_DIR = os.path.join(BASE_DIR, "assets", "overlays")
DESCRIPTION_YAML_PATH = os.path.join(BASE_DIR, "config", "descriptions","descriptions.yaml")
PRICING_FILE = os.path.join(BASE_DIR, "config", "prices", "prices.yaml")

# === HELPERS ===

def load_pricing():
    if not os.path.exists(PRICING_FILE):
        print(f"⚠️ Pricing file not found at {PRICING_FILE}")
        return {}
    with open(PRICING_FILE, 'r') as f:
        return yaml.safe_load(f) or {}

def load_descriptions():
    if not os.path.exists(DESCRIPTION_YAML_PATH):
        return {}
    with open(DESCRIPTION_YAML_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def load_colors(category):
    yaml_path = os.path.join(COLOR_CONFIG_DIR, f"{category}.yaml")
    if not os.path.exists(yaml_path):
        print(f"⚠️ No color YAML found for category '{category}'")
        return []
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
        return data.get("colors", [])

def apply_mask(base_img, color_img, mask_img):
    if mask_img.mode != "L":
        mask_img = mask_img.convert("L")
    return Image.composite(color_img, base_img, mask_img)

def is_light_image(image):
    stat = ImageStat.Stat(image.convert("L"))
    return stat.mean[0] > 127

# === SWATCH GENERATION (runs only once per color) ===
def ensure_swatch(color_def):
    swatch_output_path = os.path.join(STATIC_SWATCH_DIR, color_def["image"])
    if os.path.exists(swatch_output_path):
        return

    color_img_path = os.path.join(STATIC_COLOR_DIR, color_def["image"])
    if not os.path.exists(color_img_path):
        print(f"⛔ Missing color file for swatch: {color_def['image']}")
        return

    os.makedirs(STATIC_SWATCH_DIR, exist_ok=True)
    color = Image.open(color_img_path).convert("RGBA").resize((64,64))
    if color.mode == "RGBA":
        color = color.convert("RGB")
    color.save(swatch_output_path)
    print(f"🎨 Swatch created: {swatch_output_path}")

# === PRODUCT VARIANT GENERATION ===
def save_variant(product_folder, base_file, color_def):
    image_name = os.path.splitext(base_file)[0]
    base_path = os.path.join(BASE_IMG_DIR, base_file)
    mask_path = os.path.join(MASK_IMG_DIR, f"{image_name}_mask.png")
    overlay_path = os.path.join(OVERLAY_IMG_DIR, f"{image_name}_overlay_light.png")
    output_dir = product_folder
    os.makedirs(output_dir, exist_ok=True)

    color_img_path = os.path.join(STATIC_COLOR_DIR, color_def["image"])
    if not all(os.path.exists(p) for p in [base_path, mask_path, color_img_path]):
        print(f"⛔ Missing input files for '{base_file}' and color '{color_def['name']}'")
        return None

    color_image_base = os.path.splitext(color_def["image"])[0]
    output_filename = f"{image_name}_{color_image_base}.webp"
    output_path = os.path.join(output_dir, output_filename)

    # Incremental: skip if file already exists
    if os.path.exists(output_path):
        print(f"⏭️ Skipping existing image: {output_path}")
        return color_def

    base = Image.open(base_path).convert("RGBA")
    color = Image.open(color_img_path).convert("RGBA").resize(base.size)
    mask = Image.open(mask_path).resize(base.size)
    output = apply_mask(base, color, mask)

    # Overlay based on brightness
    if is_light_image(output):
        overlay_path = os.path.join(OVERLAY_IMG_DIR, f"{image_name}_overlay_dark.png")

    if os.path.exists(overlay_path):
        overlay = Image.open(overlay_path).resize(base.size)
        output = Image.alpha_composite(output, overlay)

    # Downscale to ~1MP for faster load
    max_pixels = 1_000_000
    if output.width * output.height > max_pixels:
        scale = (max_pixels / (output.width * output.height)) ** 0.5
        output = output.resize((int(output.width*scale), int(output.height*scale)), Image.LANCZOS)

    output.save(output_path, format="WEBP", quality=85, method=6)
    print(f"✅ Saved WebP: {output_path}")

    return color_def

# === WRITE INDEX.MD ===
def write_index_md(product_folder, title, color_defs, default_color_img, pricing=None, description_text=""):
    index_md_path = os.path.join(product_folder, "index.md")
    with open(index_md_path, "w", encoding="utf-8") as f:
        f.write(f"---\ntitle: \"{title}\"\nmarkup: \"html\"\n")

        if pricing:
            for key in ["cost_price", "discount", "selling_price", "launch_date"]:
                if key in pricing:
                    f.write(f"{key}: {pricing[key]}\n")

        f.write("colors:\n")
        for c in color_defs:
            color_image_base = os.path.splitext(c['image'])[0]
            f.write(f"  - name: {c['name']}\n")
            f.write(f"    image: {os.path.basename(product_folder)}_{color_image_base}.webp\n")
            f.write(f"    color: \"{c['color']}\"\n")

        default_color_base = os.path.splitext(default_color_img)[0]
        f.write(f"default_color: {os.path.basename(product_folder)}_{default_color_base}.webp\n")
        f.write("---\n\n")

        if description_text:
            f.write(f"{description_text}\n")

    print(f"📝 index.md updated for {title}")

# === MAIN PRODUCT GENERATION ===
def generate_for_product(product_folder, pricing_data):
    product_name = os.path.basename(product_folder)
    category = os.path.basename(os.path.dirname(product_folder))
    print(f"\n🔍 Processing: {product_name} (Category: {category})")

    colors = load_colors(category)
    if not colors:
        print(f"⚠️ Skipping {product_name} due to missing colors.")
        return

    # Generate swatches (once per color)
    for color_def in colors:
        ensure_swatch(color_def)

    # Find base file
    base_file = next(
        (f for f in os.listdir(BASE_IMG_DIR) if os.path.splitext(f)[0]==product_name and f.lower().endswith((".jpg",".jpeg",".png"))),
        None
    )
    if not base_file:
        print(f"❌ No base image found for '{product_name}'")
        return

    generated_defs = []
    for color_def in colors:
        result = save_variant(product_folder, base_file, color_def)
        if result and result not in generated_defs:
            generated_defs.append(result)

    if not generated_defs:
        print(f"🚫 No variants generated for {product_name}")
        return

    default_color_img = random.choice(generated_defs)["image"]

    # Descriptions
    descriptions = load_descriptions()
    category_desc = descriptions.get(category, "")
    product_desc = descriptions.get(product_name, "")
    description_text = "  \n".join([d for d in [category_desc, product_desc] if d]).strip() or "Description coming soon"

    # Pricing
    category_prices = pricing_data.get(category, {})
    default_prices = category_prices.get("_default", {})
    product_prices = category_prices.get(product_name, {})
    pricing = {
        "cost_price": product_prices.get("cost_price", default_prices.get("cost_price", 0)),
        "discount": product_prices.get("discount", default_prices.get("discount", 0)),
        "selling_price": product_prices.get("selling_price", default_prices.get("selling_price", 0)),
        "launch_date": product_prices.get("launch_date", default_prices.get("launch_date", "TBD")),
    }

    write_index_md(product_folder, product_name.replace("-", " ").title(), generated_defs, default_color_img, pricing, description_text)

# === MAIN SCRIPT ===
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["full","incremental"], default="full")
    parser.add_argument("--product")
    args = parser.parse_args()

    pricing_data = load_pricing()
    print("✅ Script started")
    print(f"📦 Arguments: mode={args.mode}, product={args.product}\n")

    # STEP 1: Scan base images and create folders if missing
    for filename in os.listdir(BASE_IMG_DIR):
        if not filename.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        product_name, _ = os.path.splitext(filename)

        for category_file in os.listdir(COLOR_CONFIG_DIR):
            category = os.path.splitext(category_file)[0]
            category_path = os.path.join(CONTENT_PRODUCTS_DIR, category)
            product_folder = os.path.join(category_path, product_name)
            if os.path.exists(category_path) and not os.path.exists(product_folder):
                os.makedirs(product_folder, exist_ok=True)
                print(f"📁 Created missing product folder: {product_folder}")

    # STEP 2: Loop through product folders
    for category in os.listdir(CONTENT_PRODUCTS_DIR):
        category_path = os.path.join(CONTENT_PRODUCTS_DIR, category)
        if not os.path.isdir(category_path):
            continue
        for product in os.listdir(category_path):
            product_folder = os.path.join(category_path, product)
            if os.path.isdir(product_folder):
                generate_for_product(product_folder, pricing_data)

    print("\n✅ All variants generated successfully.")

if __name__ == "__main__":
    main()
