import os
import shutil
import time
from datetime import datetime
import requests
import qrcode
from PIL import Image, ImageEnhance
from rembg import remove
import vtracer
from rectpack import newPacker
from reportlab.lib import pagesizes
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
import gradio as gr

# Setup local working directories inside the server container
output_dir = "output_pdfs"
failed_dir = "failed_drops"
os.makedirs(output_dir, exist_ok=True)
os.makedirs(failed_dir, exist_ok=True)

PRICE_PER_ITEM = 3.00
PRODUCT_NAME = "Correx Party Board (A0)"

def convert_to_cmyk_press(pil_img):
    return pil_img.convert('CMYK')

def validate_preflight(file_path):
    try:
        with Image.open(file_path) as img:
            img.verify()
        with Image.open(file_path) as img:
            w, h = img.size
            if w < 1000 or h < 1000:
                return False, f"Low Resolution ({w}x{h}px). Minimum required: 1000x1000px."
            return True, "Pass"
    except Exception as e:
        return False, f"Corrupted or Unreadable Image: {e}"

def process_image_file(file_path, brightness=1.0, contrast=1.0, saturation=1.0, paper_size='A4', cols=2, rows=3):
    if not file_path:
        return None, "⚠️ Please upload an image file."

    filename = os.path.basename(file_path)
    base_name, _ = os.path.splitext(filename)

    # 1. Preflight Inspection
    valid, reason = validate_preflight(file_path)
    if not valid:
        shutil.copy(file_path, os.path.join(failed_dir, filename))
        return None, f"🚨 Preflight Failed for {filename}: {reason}"

    # 2. Image Processing & BG Removal
    img = Image.open(file_path)
    if brightness != 1.0: img = ImageEnhance.Brightness(img).enhance(brightness)
    if contrast != 1.0: img = ImageEnhance.Contrast(img).enhance(contrast)
    if saturation != 1.0: img = ImageEnhance.Color(img).enhance(saturation)

    no_bg_image = remove(img)
    temp_png_path = f"{base_name}_no_bg.png"
    no_bg_image.save(temp_png_path, 'PNG')

    # 3. Vectorization
    output_svg_path = f"{base_name}.svg"
    vtracer.convert_image_to_svg_py(temp_png_path, output_svg_path, colormode='color', mode='spline', filter_speckle=4)

    # 4. Tracking QR Code
    qr = qrcode.QRCode(version=1, border=1)
    track_url = f"https://yourprintshop.com/jobs/{base_name}"
    qr.add_data(track_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color='black', back_color='white')
    temp_qr_path = f"{base_name}_qr.png"
    qr_img.save(temp_qr_path)

    # 5. PDF Generation
    pdf_path = os.path.join(output_dir, f"{base_name}_production_output.pdf")
    size_map = {'LETTER': pagesizes.letter, 'A4': pagesizes.A4, 'A3': pagesizes.A3, 'A2': pagesizes.A2}
    p_size = size_map.get(paper_size.upper(), pagesizes.A4)
    c = canvas.Canvas(pdf_path, pagesize=p_size)
    width, height = p_size
    margin = 0.5 * inch

    item_w = (width - 2*margin) / cols
    item_h = (height - 2*margin - 0.5*inch) / rows
    for r in range(rows):
        for col in range(cols):
            x_pos = margin + (col * item_w)
            y_pos = margin + 0.5*inch + (r * item_h)
            c.rect(x_pos, y_pos, item_w, item_h, stroke=1, fill=0)
            c.drawImage(temp_png_path, x_pos+2, y_pos+2, width=item_w-4, height=item_h-4, mask='auto')

    # Color Bars & Registration Marks
    colors = [(1,0,0), (0,1,0), (0,0,1), (1,1,0), (1,0,1), (0,1,1)]
    for idx, color in enumerate(colors):
        c.setFillColorRGB(*color)
        c.rect(margin + (idx*12), height - margin + 4, 10, 6, fill=1, stroke=0)

    c.drawImage(temp_qr_path, width - margin - 0.6*inch, height - margin + 2, width=0.6*inch, height=0.6*inch)
    c.setFont('Helvetica', 7)
    c.setFillColorRGB(0.3, 0.3, 0.3)
    c.drawString(margin, margin, f"Job Ref: {base_name} | Product: {PRODUCT_NAME} | Price: £{PRICE_PER_ITEM:.2f}")
    c.showPage()
    c.save()

    # Cleanup temp files
    for tmp in [temp_png_path, output_svg_path, temp_qr_path]:
        if os.path.exists(tmp): os.remove(tmp)

    return pdf_path, f"✅ Job {base_name} compiled into CMYK PDF!"

def dashboard_process(input_file, brightness, contrast, saturation, paper_size, cols, rows):
    pdf_path, status = process_image_file(input_file.name if input_file else None, brightness, contrast, saturation, paper_size, cols, rows)
    return pdf_path, status

with gr.Blocks(title="Enterprise Print Factory OS") as demo:
    gr.Markdown("# 🖨️ Atown Printers — Print Factory OS")
    gr.Markdown("Automatic background removal, vectorization, CMYK grid PDF generation, and pre-flight validation.")
    
    with gr.Row():
        with gr.Column():
            file_input = gr.File(label="Drop Master Design File")
            paper_size = gr.Dropdown(['A4', 'A3', 'A2', 'Letter'], value='A4', label='Substrate Format')
            cols = gr.Slider(1, 6, value=2, step=1, label='Grid Columns')
            rows = gr.Slider(1, 6, value=3, step=1, label='Grid Rows')
            brightness = gr.Slider(0.5, 2.0, value=1.0, label='Brightness')
            contrast = gr.Slider(0.5, 2.0, value=1.0, label='Contrast')
            saturation = gr.Slider(0.5, 2.0, value=1.0, label='Saturation')
            btn = gr.Button("🚀 Compile Print Batch Job", variant="primary")
        
        with gr.Column():
            status_output = gr.Textbox(label="Job Status")
            pdf_output = gr.File(label="Download CMYK Print Sheet PDF")

    btn.click(dashboard_process, inputs=[file_input, brightness, contrast, saturation, paper_size, cols, rows], outputs=[pdf_output, status_output])

if __name__ == "__main__":
    # REQUIRED FOR RENDER DEPLOYMENT
    demo.launch(server_name="0.0.0.0", server_port=10000)
