import os
import re
import requests
from fpdf import FPDF  # type: ignore


FONT_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "fonts")
FONT_PATH = os.path.join(FONT_DIR, "NanumGothic.ttf")
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Regular.ttf"

def ensure_font_downloaded():
    """한글 폰트(나눔고딕)가 없을 경우 자동으로 인터넷에서 다운로드합니다."""
    if not os.path.exists(FONT_DIR):
        os.makedirs(FONT_DIR, exist_ok=True)
    if not os.path.exists(FONT_PATH):
        print(f"[PDF Compiler] 한글 폰트 다운로드 중... ({FONT_URL})")
        try:
            res = requests.get(FONT_URL, timeout=15)
            if res.status_code == 200:
                with open(FONT_PATH, "wb") as f:
                    f.write(res.content)
                print("[PDF Compiler] 한글 폰트 다운로드 완료.")
            else:
                print(f"[PDF Compiler] 폰트 다운로드 실패 (상태 코드: {res.status_code})")
        except Exception as e:
            print(f"[PDF Compiler] 폰트 다운로드 중 에러 발생: {e}")

class MarkdownPDF(FPDF):
    def __init__(self):
        super().__init__()
        ensure_font_downloaded()
        if os.path.exists(FONT_PATH):
            self.add_font("NanumGothic", "", FONT_PATH, uni=True)
            self.font_family_name = "NanumGothic"
        else:
            self.font_family_name = "Helvetica"
        
        self.set_auto_page_break(auto=True, margin=15)
        self.add_page()

    def header(self):
        self.set_font(self.font_family_name, "", 9)
        self.set_text_color(128, 128, 128)
        self.cell(0, 8, "GitHub 변경사항 분석 보고서 (LangGraph HITL System)", border=0, new_x="LMARGIN", new_y="NEXT", align="R")
        self.ln(2)

    def footer(self):
        self.set_y(-15)
        self.set_font(self.font_family_name, "", 9)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"페이지 {self.page_no()}", align="C")

def markdown_to_pdf(markdown_text: str, output_pdf_path: str):
    """
    마크다운 텍스트를 파싱하여 PDF 파일로 변환 및 저장합니다.
    """
    os.makedirs(os.path.dirname(output_pdf_path), exist_ok=True)
    pdf = MarkdownPDF()
    font_name = pdf.font_family_name

    lines = markdown_text.split("\n")
    in_code_block = False

    for line in lines:
        stripped = line.strip()
        
        # 코드 블록 처리
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue

        if in_code_block:
            pdf.set_font(font_name, "", 9)
            pdf.set_fill_color(245, 245, 245)
            pdf.set_text_color(50, 50, 50)
            pdf.cell(0, 6, f"  {line}", new_x="LMARGIN", new_y="NEXT", fill=True)
            continue

        # 빈 줄
        if not stripped:
            pdf.ln(4)
            continue

        # 헤더 H1 (# )
        if stripped.startswith("# "):
            pdf.ln(4)
            pdf.set_font(font_name, "", 18)
            pdf.set_text_color(20, 50, 120)
            pdf.multi_cell(0, 10, stripped[2:].strip(), new_x="LMARGIN", new_y="NEXT")
            pdf.set_draw_color(200, 200, 200)
            pdf.line(10, pdf.get_y(), 200, pdf.get_y())
            pdf.ln(4)

        # 헤더 H2 (## )
        elif stripped.startswith("## "):
            pdf.ln(3)
            pdf.set_font(font_name, "", 14)
            pdf.set_text_color(40, 80, 160)
            pdf.multi_cell(0, 8, stripped[3:].strip(), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)

        # 헤더 H3 (### )
        elif stripped.startswith("### "):
            pdf.ln(2)
            pdf.set_font(font_name, "", 12)
            pdf.set_text_color(60, 60, 60)
            pdf.multi_cell(0, 7, stripped[4:].strip(), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)

        # 리스트 항목 (- 또는 * 또는 1.)
        elif stripped.startswith("- ") or stripped.startswith("* ") or re.match(r"^\d+\.\s", stripped):
            pdf.set_font(font_name, "", 10)
            pdf.set_text_color(30, 30, 30)
            clean_item = re.sub(r"^(\-|\*|\d+\.)\s*", "", stripped)
            clean_item = clean_item.replace("**", "").replace("`", "")
            pdf.multi_cell(0, 6, f"• {clean_item}", new_x="LMARGIN", new_y="NEXT")

        # 일반 본문 텍스트
        else:
            pdf.set_font(font_name, "", 10)
            pdf.set_text_color(40, 40, 40)
            clean_text = stripped.replace("**", "").replace("`", "")
            pdf.multi_cell(0, 6, clean_text, new_x="LMARGIN", new_y="NEXT")

    pdf.output(output_pdf_path)
    print(f"[PDF Compiler] PDF 생성 완료: {output_pdf_path}")
    return output_pdf_path
