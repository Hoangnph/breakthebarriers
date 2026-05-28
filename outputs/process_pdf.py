import os
import shutil
import glob
import subprocess
from PIL import Image

def is_blank_image(image_path):
    try:
        with Image.open(image_path) as img:
            extrema = img.getextrema()
            if isinstance(extrema[0], tuple):
                for band_min, band_max in extrema:
                    if band_min != band_max:
                        return False
                return True
            else:
                return extrema[0] == extrema[1]
    except Exception as e:
        print(f"Lỗi kiểm tra ảnh {image_path}: {e}")
        return False

def main():
    base_dir = "/Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator/outputs"
    pdf_path = "/Users/autoeyes/Project/AI_Educations/Agent_Skill_Creator/assets/Agentic_Design_Patterns.pdf"
    
    # 1. Dọn dẹp outputs/ (chừa lại script này)
    for f in os.listdir(base_dir):
        p = os.path.join(base_dir, f)
        if os.path.isfile(p) and not p.endswith('.py'):
            os.remove(p)
        elif os.path.isdir(p) and f != "Agentic_Design_Patterns":
            shutil.rmtree(p)

    target_dir = os.path.join(base_dir, "Agentic_Design_Patterns")
    if os.path.exists(target_dir):
        shutil.rmtree(target_dir)

    # 2. Chạy pdftohtml
    print("Đang chạy lệnh pdftohtml cho toàn bộ trang...")
    subprocess.run(["/opt/homebrew/bin/pdftohtml", "-c", pdf_path, os.path.join(base_dir, "Agentic_Design_Patterns.html")], check=True)

    # 3. Tạo cấu trúc thư mục mới
    print("Cấu trúc lại thư mục...")
    pages_dir = os.path.join(target_dir, "pages")
    images_dir = os.path.join(target_dir, "images")
    os.makedirs(pages_dir, exist_ok=True)
    os.makedirs(images_dir, exist_ok=True)

    # 4. Di chuyển và sửa file index
    for idx_file, target_file in [("Agentic_Design_Patterns.html", "index.html"), ("Agentic_Design_Patterns_ind.html", "toc.html")]:
        src = os.path.join(base_dir, idx_file)
        if os.path.exists(src):
            shutil.move(src, os.path.join(target_dir, target_file))

    # Fix link trong toc.html
    toc_path = os.path.join(target_dir, "toc.html")
    if os.path.exists(toc_path):
        with open(toc_path, 'r', encoding='ISO-8859-1') as f:
            content = f.read()
        content = content.replace('href="Agentic_Design_Patterns-', 'href="pages/Agentic_Design_Patterns-')
        with open(toc_path, 'w', encoding='ISO-8859-1') as f:
            f.write(content)

    # Fix link trong index.html
    main_path = os.path.join(target_dir, "index.html")
    if os.path.exists(main_path):
        with open(main_path, 'r', encoding='ISO-8859-1') as f:
            content = f.read()
        content = content.replace('src="Agentic_Design_Patterns_ind.html"', 'src="toc.html"')
        content = content.replace('src="Agentic_Design_Patterns-1.html"', 'src="pages/Agentic_Design_Patterns-1.html"')
        with open(main_path, 'w', encoding='ISO-8859-1') as f:
            f.write(content)

    # 5. Xử lý từng trang html & ảnh
    html_files = glob.glob(os.path.join(base_dir, "Agentic_Design_Patterns-*.html"))
    blank_count = 0
    img_count = 0

    for hf in html_files:
        basename = os.path.basename(hf)
        page_num = basename.split('-')[1].split('.')[0]
        img_name = f"Agentic_Design_Patterns{int(page_num):03d}.png"
        img_path = os.path.join(base_dir, img_name)

        is_blank = False
        if os.path.exists(img_path):
            is_blank = is_blank_image(img_path)
            if not is_blank:
                shutil.move(img_path, os.path.join(images_dir, img_name))
                img_count += 1
            else:
                os.remove(img_path)
                blank_count += 1

        # Sửa file HTML
        with open(hf, 'r', encoding='ISO-8859-1') as f:
            lines = f.readlines()
        
        with open(os.path.join(pages_dir, basename), 'w', encoding='ISO-8859-1') as f:
            for line in lines:
                if '<IMG' in line and img_name in line:
                    if is_blank:
                        continue # Xoá dòng chứa ảnh nền trắng
                    else:
                        line = line.replace(f'src="{img_name}"', f'src="../images/{img_name}"')
                elif '<DIV style="position:relative;width:918;height:1188;">' in line and is_blank:
                    line = line.replace('height:1188;">', 'height:1188;background-color:white;">')
                f.write(line)
        
        os.remove(hf)

    print(f"Hoàn tất! Đã giữ lại {img_count} ảnh có nội dung và xoá {blank_count} ảnh nền trắng.")

if __name__ == "__main__":
    main()
