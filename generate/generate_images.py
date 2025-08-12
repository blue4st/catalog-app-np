import os
import sys
import argparse
import yaml
import random
from PIL import Image
from PIL import ImageStat
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

from PIL import ImageStat

def is_light_image(image):
    stat = ImageStat.Stat(image.convert("L"))
    return stat.mean[0] > 127  # threshold for brightness

def save_variant_and_swatch(product_folder, base_file, color_def):
    image_name = os.path.splitext(base_file)[0]
    base_path = os.path.join(BASE_IMG_DIR, base_file)
    mask_path = os.path.join(MASK_IMG_DIR, f"{image_name}_mask.png")
    overlay_path = os.path.join(OVERLAY_IMG_DIR, f"{image_name}_overlay_light.png")
    category = os.path.basename(os.path.dirname(product_folder))
    output_dir = product_folder
    os.makedirs(output_dir, exist_ok=True)

    color_img_path = os.path.join(STATIC_COLOR_DIR, color_def["image"])
    swatch_output_path = os.path.join(STATIC_SWATCH_DIR, color_def["image"])
    print("🔎 Checking files:")
    print(f"   Base:  {repr(base_path)} -> {os.path.exists(base_path)}")
    print(f"   Mask:  {repr(mask_path)} -> {os.path.exists(mask_path)}")
    print(f"   Color: {repr(color_img_path)} -> {os.path.exists(color_img_path)}")
    print(f"   Overlay: {repr(overlay_path)} -> {os.path.exists(overlay_path)}")
    if not all(os.path.exists(p) for p in [base_path, mask_path, color_img_path]):
        print(f"⛔ Missing input files for '{base_file}' and color '{color_def['name']}'")
        return None

    base = Image.open(base_path).convert("RGBA")
    color = Image.open(color_img_path).convert("RGBA").resize(base.size)
    mask = Image.open(mask_path).resize(base.size)

    output = apply_mask(base, color, mask)

    # Choose overlay based on brightness of masked image
    if is_light_image(output):
        overlay_path = os.path.join(OVERLAY_IMG_DIR, f"{image_name}_overlay_dark.png")
        
    if os.path.exists(overlay_path):
        overlay = Image.open(overlay_path).resize(base.size)
        output = Image.alpha_composite(output, overlay)
    
    # Strip any extension from color_def["image"]
    color_image_base = os.path.splitext(color_def["image"])[0]
    output_filename = f"{image_name}_{color_image_base}.webp"
    output_path = os.path.join(output_dir, output_filename)

# Downscale to ~2MP for faster load
    max_pixels = 1_000_000
    current_pixels = output.width * output.height
    if current_pixels > max_pixels:
        scale = (max_pixels / current_pixels) ** 0.5
        new_width = int(output.width * scale)
        new_height = int(output.height * scale)
        output = output.resize((new_width, new_height), Image.LANCZOS)
        print(f"📏 Resized to {new_width}x{new_height} (~2MP)")
        
# Save as lossy WebP for fast load times
    output.save(output_path, format="WEBP", quality=85, method=6)  # quality 85 is a good balance
    print(f"✅ Saved WebP: {output_path}")
    
    #output.save(output_path, format="PNG")
    #print(f"✅ Saved: {output_path}")

    # Swatch generation
    swatch = color.copy().resize((64, 64))
    if swatch.mode == "RGBA":
        swatch = swatch.convert("RGB")
    swatch.save(swatch_output_path)
    print(f"🎨 Swatch created: {swatch_output_path}")

    return color_def

def write_index_md(product_folder, title, color_defs, default_color_img, pricing=None, description_text=""):
    product_name = os.path.basename(product_folder)
    index_md_path = os.path.join(product_folder, "index.md")
    with open(index_md_path, "w", encoding="utf-8") as f:
        f.write(f"---\ntitle: \"{title}\"\nmarkup: \"html\"\n")

        # Optional pricing fields
        if pricing:
            if "cost_price" in pricing:
                f.write(f"cost_price: {pricing['cost_price']}\n")
            if "discount" in pricing:
                f.write(f"discount: {pricing['discount']}\n")
            if "selling_price" in pricing:
                f.write(f"selling_price: {pricing['selling_price']}\n")
            if "launch_date" in pricing:
                f.write(f"launch_date: {pricing['launch_date']}\n")

        f.write("colors:\n")
        for c in color_defs:
            color_image_base = os.path.splitext(c['image'])[0]  # strip extension
            image_filename = f"{product_name}_{color_image_base}.webp"  # force .webp
            f.write(f"  - name: {c['name']}\n")
            f.write(f"    image: {image_filename}\n")
            f.write(f"    color: \"{c['color']}\"\n")
        
        default_color_base = os.path.splitext(default_color_img)[0]
        default_image_filename = f"{product_name}_{default_color_base}.webp"
        #default_image_filename = f"{product_name}_{default_color_img}"
        f.write(f"default_color: {default_image_filename}\n")
        f.write("---\n\n")

        if description_text:
            f.write(f"{description_text}\n")

    print(f"📝 index.md updated for {title}")

    
def generate_for_product(product_folder, pricing_data):
    product_name = os.path.basename(product_folder)
    category = os.path.basename(os.path.dirname(product_folder))
    print(f"\n🔍 Processing: {product_name} (Category: {category})")

    colors = load_colors(category)
    if not colors:
        print(f"⚠️ Skipping {product_name} due to missing colors.")
        return

    # Find base file
    base_file = None
    for ext in [".jpg", ".jpeg", ".png"]:
        candidate = f"{product_name}{ext}"
        if os.path.exists(os.path.join(BASE_IMG_DIR, candidate)):
            base_file = candidate
            break

    if not base_file:
        print(f"❌ No base image found for product '{product_name}' in {BASE_IMG_DIR}")
        return

    generated_defs = []
    for color_def in colors:
        result = save_variant_and_swatch(product_folder, base_file, color_def)
        if result and color_def not in generated_defs:
            generated_defs.append(result)

    if generated_defs:
        default_color_img = random.choice(generated_defs)["image"]

        # Get description
        descriptions = load_descriptions()
        description_text = descriptions.get(product_name, "Description coming soon.")

        # Get pricing info from YAML
        category_prices = pricing_data.get(category, {})
        default_prices = category_prices.get("_default", {})

        product_prices = category_prices.get(product_name, {})

        pricing = {
            "cost_price": product_prices.get("cost_price", default_prices.get("cost_price", 0)),
            "discount": product_prices.get("discount", default_prices.get("discount", 0)),
            "selling_price": product_prices.get("selling_price", default_prices.get("selling_price", 0)),
            "launch_date": product_prices.get("launch_date", default_prices.get("launch_date", "TBD")),
        }

        write_index_md(
            product_folder,
            product_name.replace("-", " ").title(),
            generated_defs,
            default_color_img,
            pricing,
            description_text
        )
    else:
        print(f"🚫 No variants generated for {product_name}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["full"], default="full")
    parser.add_argument("--product")
    args = parser.parse_args()
    pricing_data = load_pricing()
    print("✅ Script started")
    print("🛠️  Parsing arguments...")
    print(f"📦 Arguments: mode={args.mode}, product={args.product}\n")

    if args.mode == "full":
        print("▶️ Running generator in full mode...")
        print("📁 Available color files:")
        for f in os.listdir(STATIC_COLOR_DIR):
            print(f"- {f}")

        # STEP 1: Scan base images and create folders if missing
        for filename in os.listdir(BASE_IMG_DIR):
            if not filename.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
            product_name, _ = os.path.splitext(filename)
            
            # Guess category from color YAML files
            found_category = None
            for category_file in os.listdir(COLOR_CONFIG_DIR):
                category = os.path.splitext(category_file)[0]
                category_path = os.path.join(CONTENT_PRODUCTS_DIR, category)
                product_folder = os.path.join(category_path, product_name)
                if os.path.exists(category_path) and not os.path.exists(product_folder):
                    os.makedirs(product_folder, exist_ok=True)
                    print(f"📁 Created missing product folder: {product_folder}")
                    found_category = category
                    break
            if not found_category:
                print(f"⚠️ Could not determine category for {product_name} — no folder created.")

        # STEP 2: Loop through all existing folders
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
