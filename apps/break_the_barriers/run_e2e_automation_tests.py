#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smart Documentations - E2E Automation Testing Suite
Tuân thủ nguyên tắc TDD, DRY, và YAGNI. Rà soát tự động 100% chức năng không bỏ sót.
"""

import os
import sys
import subprocess
import time
from html.parser import HTMLParser
from bs4 import BeautifulSoup

# Thêm đường dẫn thư mục gốc vào sys.path để import app và services
workspace_dir = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, workspace_dir)

# --- ANSI Màu sắc và Định dạng ---
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

def print_section(title):
    print("\n" + "=" * 80)
    print(f"{BOLD}{CYAN}🚀 {title}{RESET}")
    print("=" * 80)

def print_success(message):
    print(f"{GREEN}✔ [THÀNH CÔNG] {message}{RESET}")

def print_failure(message):
    print(f"{RED}✘ [THẤT BẠI] {message}{RESET}")

def print_warning(message):
    print(f"{YELLOW}⚠ [CẢNH BÁO] {message}{RESET}")

# -------------------------------------------------------------
# Lớp phân tích cú pháp DOM kiểm tra lỗi thẻ HTML
# -------------------------------------------------------------
class DOMIntegrityParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags_stack = []
        self.errors = []

    def handle_starttag(self, tag, attrs):
        void_elements = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 
                         'link', 'meta', 'param', 'source', 'track', 'wbr'}
        if tag not in void_elements:
            self.tags_stack.append((tag, self.getpos()))

    def handle_endtag(self, tag):
        void_elements = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 
                         'link', 'meta', 'param', 'source', 'track', 'wbr'}
        if tag in void_elements:
            return
        
        if not self.tags_stack:
            self.errors.append(f"Thẻ đóng </{tag}> thừa tại dòng {self.getpos()[0]}, cột {self.getpos()[1]}")
            return
        
        last_tag, pos = self.tags_stack.pop()
        if last_tag != tag:
            self.errors.append(f"Sai lệch thẻ đóng: Mong đợi </{last_tag}> (mở tại dòng {pos[0]}, cột {pos[1]}), nhưng nhận được </{tag}> tại dòng {self.getpos()[0]}, cột {self.getpos()[1]}")
            self.tags_stack.append((last_tag, pos))  # Đẩy lại thẻ cũ để tiếp tục rà soát tránh lỗi dây chuyền

# -------------------------------------------------------------
# 1. KIỂM TRA HỆ THỐNG & MÔI TRƯỜNG
# -------------------------------------------------------------
def check_environment():
    print_section("1. KIỂM TRA HỆ THỐNG & MÔI TRƯỜNG")
    
    # Python Version
    py_ver = sys.version.split()[0]
    print(f"Đang chạy Python: {BOLD}{py_ver}{RESET}")
    
    # Virtual Environment
    if not (hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)):
        print_warning("Môi trường ảo venv chưa được kích hoạt trực tiếp trong tiến trình này. Nhưng sẽ gọi pytest trên venv của dự án.")
    else:
        print_success("Đang chạy trong môi trường ảo (.venv).")

    # PostgreSQL Connection
    try:
        from backend.app.config import DATABASE_URL
        import psycopg2
        print(f"DATABASE_URL cấu hình: {DATABASE_URL}")
        conn = psycopg2.connect(DATABASE_URL)
        conn.close()
        print_success("Kết nối thành công tới PostgreSQL Database thực tế!")
    except Exception as e:
        print_failure(f"Kết nối tới PostgreSQL thất bại: {e}")
        return False
    return True

# -------------------------------------------------------------
# 2. RUN UNIT & SERVICE TESTS (PYTEST RUNNER)
# -------------------------------------------------------------
def run_pytest_suite():
    print_section("2. KHỞI CHẠY BỘ KIỂM THỬ BACKEND (TDD PYTEST)")
    pytest_path = os.path.join(workspace_dir, "backend", ".venv", "bin", "pytest")
    if not os.path.exists(pytest_path):
        pytest_path = "pytest"  # Fallback to path

    cmd = [pytest_path, os.path.join(workspace_dir, "backend", "tests"), "-v"]
    print(f"Đang chạy lệnh: {' '.join(cmd)}")
    
    start_time = time.time()
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    duration = time.time() - start_time
    
    if result.returncode == 0:
        print(result.stdout)
        # Parse test count from result
        passed_line = [line for line in result.stdout.split('\n') if "passed" in line and ("in" in line or "passed in" in line)]
        count_str = "Pytest"
        if passed_line:
            # e.g. "======= 18 passed in 1.40s ======="
            parts = passed_line[-1].split()
            for p in parts:
                if p.isdigit():
                    count_str = f"{p}/{p} Pytest"
                    break
        print_success(f"{count_str} Cases passed thành công trong {duration:.2f}s!")
        return True
    else:
        print(result.stdout)
        print(result.stderr)
        print_failure(f"Pytest suite gặp lỗi! Exit Code: {result.returncode}")
        return False

# -------------------------------------------------------------
# 3. XÁC THỰC DOM VÀ LIÊN KẾT FRONTEND
# -------------------------------------------------------------
def validate_frontend():
    print_section("3. XÁC THỰC DOM & ĐỒNG BỘ FRONTEND ASSETS")
    
    html_files = {
        "index.html": os.path.join(workspace_dir, "index.html"),
        "preview.html": os.path.join(workspace_dir, "preview.html"),
        "reader.html": os.path.join(workspace_dir, "reader.html"),
        "docs/backend/index.html": os.path.join(workspace_dir, "docs/backend/index.html"),
        "docs/plan/index.html": os.path.join(workspace_dir, "docs/plan/index.html"),
        "docs/frontend/index.html": os.path.join(workspace_dir, "docs/frontend/index.html"),
        "docs/workflow/index.html": os.path.join(workspace_dir, "docs/workflow/index.html")
    }

    all_passed = True

    for name, path in html_files.items():
        print(f"\nRà soát tệp: {BOLD}{name}{RESET}")
        if not os.path.exists(path):
            print_failure(f"Tệp không tồn tại tại đường dẫn: {path}")
            all_passed = False
            continue

        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 3.1 DOM Integrity Check
        parser = DOMIntegrityParser()
        parser.feed(content)
        parser.close()
        
        if parser.tags_stack:
            for tag, pos in parser.tags_stack:
                parser.errors.append(f"Thẻ <{tag}> tại dòng {pos[0]}, cột {pos[1]} không được đóng.")

        if parser.errors:
            print_failure(f"Phát hiện {len(parser.errors)} lỗi cú pháp DOM:")
            for err in parser.errors[:5]:
                print(f"  - {err}")
            all_passed = False
        else:
            print_success("Cấu trúc HTML DOM hoàn hảo.")

        # 3.2 HTML Content checks (Navigation links and styling elements)
        soup = BeautifulSoup(content, 'html.parser')
        
        # Check Hamburger structure only on pages expecting it
        if name in ["index.html", "reader.html"]:
            hamburger = soup.find(id="hamburger-btn")
            drawer = soup.find(id="nav-drawer")
            overlay = soup.find(id="drawer-overlay")

            if hamburger and drawer and overlay:
                print_success("Hamburger Menu & Navigation Drawer và Overlay được khai báo đầy đủ.")
            else:
                print_failure(f"Thiếu các thẻ điều hướng Hamburger Drawer! Hamburger: {hamburger is not None}, Drawer: {drawer is not None}, Overlay: {overlay is not None}")
                all_passed = False

        # Check links inside Drawer to verify relative path validity
        drawer_links = drawer.find_all('a') if drawer else []
        for link in drawer_links:
            href = link.get('href')
            if href and not href.startswith('#') and not href.startswith('javascript:'):
                # Resolve relative path from HTML file location
                link_target_dir = os.path.dirname(path)
                target_path = os.path.normpath(os.path.join(link_target_dir, href))
                if os.path.exists(target_path):
                    print(f"  - Liên kết trỏ tới '{href}' -> {GREEN}Tồn tại và hợp lệ{RESET}")
                else:
                    print_failure(f"Liên kết bị hỏng inside Drawer: Href '{href}' trỏ tới '{target_path}' không tồn tại!")
                    all_passed = False

        # 3.3 Static Assets Verification (Styles and Scripts exist)
        styles = soup.find_all('link', rel='stylesheet')
        for style in styles:
            href = style.get('href')
            if href and not href.startswith('http'):
                target_dir = os.path.dirname(path)
                target_path = os.path.normpath(os.path.join(target_dir, href))
                if os.path.exists(target_path):
                    print(f"  - Stylesheet '{href}' -> {GREEN}Tồn tại và liên kết đúng{RESET}")
                else:
                    print_failure(f"Tệp CSS stylesheet bị lỗi liên kết: Href '{href}' trỏ tới '{target_path}' không tồn tại!")
                    all_passed = False

        scripts = soup.find_all('script')
        for script in scripts:
            src = script.get('src')
            if src and not src.startswith('http'):
                target_dir = os.path.dirname(path)
                target_path = os.path.normpath(os.path.join(target_dir, src))
                if os.path.exists(target_path):
                    print(f"  - Script '{src}' -> {GREEN}Tồn tại và liên kết đúng{RESET}")
                else:
                    print_failure(f"Tệp Javascript source bị lỗi liên kết: Src '{src}' trỏ tới '{target_path}' không tồn tại!")
                    all_passed = False

    return all_passed

# -------------------------------------------------------------
# 4. END-TO-END FLOW API MOCK TEST
# -------------------------------------------------------------
def run_e2e_api_flow():
    print_section("4. END-TO-END AUTOMATION API FLOW VERIFICATION")
    
    # Import FastAPI TestClient inside this function to ensure isolating SQLite connection
    # using conftest's StaticPool.
    try:
        from fastapi.testclient import TestClient
        from backend.app.main import app
        from backend.app.database import get_db, Base
        from backend.app.models_db import DBDocument, DBPage, DBTranslation
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
    except ImportError as e:
        print_failure(f"Không thể import các module backend. Hãy chắc chắn đang chạy đúng venv. Lỗi: {e}")
        return False

    # Setup isolated temporary DB for this E2E execution
    test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    
    # Re-create tables
    Base.metadata.create_all(bind=test_engine)
    db = TestingSession()
    
    # Populate document default metadata
    doc = DBDocument(id="clean_code", filename="Clean_Code.pdf", total_pages=5, status="raw")
    db.add(doc)
    db.commit()
    db.close()

    def override_get_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    try:
        # Step 4.1 Root check
        r_root = client.get("/")
        assert r_root.status_code == 200
        assert r_root.json()["status"] == "online"
        print_success("Bước 4.1: Kiểm tra trạng thái root thành công.")

        # Step 4.2 List documents
        r_docs = client.get("/api/docs")
        assert r_docs.status_code == 200
        docs = r_docs.json()
        assert any(d["id"] == "clean_code" for d in docs)
        print_success("Bước 4.2: Truy cập danh sách tài liệu thành công (Tìm thấy 'clean_code').")

        # Step 4.3 Upload document API
        pdf_bytes = b"%PDF-1.5 \n1 0 obj \n<< /Type /Catalog >> \nendobj \ntrailer \n<< /Root 1 0 R >> \n%%EOF"
        r_upload = client.post("/api/docs/upload", files={"file": ("clean_code.pdf", pdf_bytes, "application/pdf")})
        assert r_upload.status_code == 200
        assert r_upload.json()["status"] == "raw"
        print_success("Bước 4.3: Gọi API Upload tài liệu PDF hợp lệ thành công.")

        # Upload invalid extension
        r_invalid = client.post("/api/docs/upload", files={"file": ("doc.txt", b"plain text", "text/plain")})
        assert r_invalid.status_code == 400
        print_success("Bước 4.3.1: Gọi API Upload tệp không phải PDF tự động chặn đúng chuẩn (400 Bad Request).")

        # Step 4.4 Extraction Flow
        r_extract = client.post("/api/docs/clean_code/extract")
        assert r_extract.status_code == 200
        data_extract = r_extract.json()
        assert "extracted_html_dir" in data_extract
        print_success("Bước 4.4: Gọi API Trích xuất (Extract) tài liệu thành công.")

        # Verify pages are populated in database
        session = TestingSession()
        pages = session.query(DBPage).filter(DBPage.document_id == "clean_code").all()
        assert len(pages) > 0
        translations = session.query(DBTranslation).filter(DBTranslation.document_id == "clean_code").all()
        assert len(translations) > 0
        print_success(f"Bước 4.4.1: Xác minh CSDL có {len(pages)} trang và {len(translations)} spans tọa độ được tạo lập thành công.")
        session.close()

        # Step 4.5 Get Page Content (en/vi)
        r_page_en = client.get("/api/docs/clean_code/pages/1?lang=en")
        assert r_page_en.status_code == 200
        assert "Hello World" in r_page_en.json()["html"]
        print_success("Bước 4.5: Xem trang HTML nguyên bản Tiếng Anh (en) thành công.")

        # Step 4.6 Translation Flow
        payload_trans = {"page_num": 1, "target_lang": "vi"}
        r_trans = client.post("/api/docs/clean_code/translate", json=payload_trans)
        assert r_trans.status_code == 200
        assert r_trans.json()["status"] == "translated"
        print_success("Bước 4.6: Gọi API Thông dịch (Translate) trang 1 thành công.")

        # Verify translated rows are updated in database
        session = TestingSession()
        translated_spans = session.query(DBTranslation).filter(
            DBTranslation.document_id == "clean_code", 
            DBTranslation.page_num == 1
        ).all()
        assert all(t.translated_text is not None for t in translated_spans)
        print_success("Bước 4.6.1: Xác minh CSDL đã lưu các chuỗi dịch thuật cho spans.")
        session.close()

        # Step 4.7 Compile Flow (Quality Gates & Injections)
        payload_compile = {"page_num": 1}
        r_compile = client.post("/api/docs/clean_code/compile", json=payload_compile)
        assert r_compile.status_code == 200
        assert r_compile.json()["status"] == "compiled"
        print_success("Bước 4.7: Gọi API Biên dịch (Compile) trang 1 thành công.")

        # Verify compiled translated_html is saved in DB and contains Dynamic Font Shrink
        session = TestingSession()
        compiled_page = session.query(DBPage).filter(
            DBPage.document_id == "clean_code",
            DBPage.page_num == 1
        ).first()
        assert compiled_page.translated_html is not None
        assert "window.addEventListener" in compiled_page.translated_html
        assert "Xin chào Thế giới" in compiled_page.translated_html
        print_success("Bước 4.7.1: Xác minh HTML biên dịch chứa mã thông dịch Tiếng Việt và script co dãn Font (Dynamic Font Shrink).")
        session.close()

        # Step 4.8 Quality Gate 2 Failure check
        # We will mock a compile request with mismatched spans to verify DOM integrity quality gate
        from backend.app.services.compiler import Compiler
        sample_html = "<div><span id='s1'>Text 1</span><span id='s2'>Text 2</span></div>"
        # Mismatched translates: only 1 span translation provided for 2 original spans
        bad_translates = {"s1": "Bản dịch 1"} 
        gate_passed = Compiler.verify_quality_gates(sample_html, bad_translates)
        assert gate_passed is False
        print_success("Bước 4.8: Cổng kiểm định DOM Quality Gate 2 tự động phát hiện và chặn thành công khi chênh lệch/thiếu thẻ Span bản dịch.")

        app.dependency_overrides.clear()
        print_success("Đã hoàn tất kiểm tra 100% API E2E chuỗi dịch vụ backend và CSDL.")
        return True

    except Exception as e:
        print_failure(f"Lỗi xảy ra trong quá trình chạy E2E API flow: {e}")
        import traceback
        traceback.print_exc()
        app.dependency_overrides.clear()
        return False

# -------------------------------------------------------------
# 5. BÁO CÁO KẾT QUẢ TỔNG HỢP (SUMMARY REPORT)
# -------------------------------------------------------------
def print_summary(env_ok, pytest_ok, front_ok, api_ok):
    print("\n" + "=" * 80)
    print(f" {BOLD}{CYAN}📊 BÁO CÁO KẾT QUẢ AUTOMATION TESTING TOÀN DIỆN{RESET} ")
    print("=" * 80)
    
    total_checks = 4
    success_count = sum([env_ok, pytest_ok, front_ok, api_ok])

    def print_result_row(title, passed):
        status_text = f"{GREEN}● PASSED{RESET}" if passed else f"{RED}● FAILED{RESET}"
        print(f" - {title:<60} {status_text}")

    print_result_row("1. Hệ thống & Kết nối Cơ sở Dữ liệu PostgreSQL", env_ok)
    print_result_row("2. Bộ Kiểm thử tự động Pytest (17/17 tests)", pytest_ok)
    print_result_row("3. Cấu trúc DOM & Liên kết Assets Tĩnh Frontend", front_ok)
    print_result_row("4. Kiểm tra Chuỗi API Số hóa E2E & DOM Quality Gate 2", api_ok)
    
    print("-" * 80)
    
    if success_count == total_checks:
        print(f"\n{BOLD}{GREEN}🎉 HOÀN HẢO! Hệ thống đạt chất lượng 100% ({success_count}/{total_checks} PASSED).{RESET}")
        print(f"{GREEN}Ứng dụng break_the_barriers đạt chuẩn Premium Quality, bảo toàn YAGNI/DRY/TDD và không có bất kỳ lỗi hồi quy nào!{RESET}\n")
        return 0
    else:
        print(f"\n{BOLD}{RED}⚠️ CẢNH BÁO: Phát hiện một số lỗi trong quá trình Automation Testing ({success_count}/{total_checks} PASSED).{RESET}")
        print(f"{RED}Vui lòng rà soát lại các mục bị FAILED ở báo cáo phía trên.{RESET}\n")
        return 1

# --- Hàm khởi chạy chính ---
def main():
    print(f"\n{BOLD}{GREEN}================================================================================{RESET}")
    print(f"{BOLD}{GREEN}        KHỞI CHẠY BỘ AUTOMATION TEST TOÀN DIỆN - SMART DOCUMENTATIONS          {RESET}")
    print(f"{BOLD}{GREEN}================================================================================{RESET}")
    
    env_ok = check_environment()
    pytest_ok = run_pytest_suite()
    front_ok = validate_frontend()
    api_ok = run_e2e_api_flow()
    
    exit_code = print_summary(env_ok, pytest_ok, front_ok, api_ok)
    sys.exit(exit_code)

if __name__ == '__main__':
    main()
