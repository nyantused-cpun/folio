# -*- coding: utf-8 -*-
"""生成 doc-extract 自测样本（pdf/docx/pptx）到 _scratch/。

放 tests/ 安全目录（guard 白名单），仅用于 CLI 新命令冒烟测试。
纯本地生成：pymupdf / python-docx / python-pptx，不写 output/ 交付物。
"""
import os

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_scratch")
os.makedirs(OUT_DIR, exist_ok=True)


def gen_pdf(path):
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "doc-extract 测试 PDF\n第 1 页标题\n正文行 A\n表格数据 123", fontsize=12)
    page2 = doc.new_page()
    page2.insert_text((72, 72), "第二页内容：金额 9999.50 元", fontsize=12)
    doc.save(path)
    doc.close()
    print("pdf ok:", path)


def gen_docx(path):
    from docx import Document
    doc = Document()
    doc.add_heading("doc-extract 测试文档", 0)
    doc.add_paragraph("第一段正文：项目范围与目标。")
    table = doc.add_table(rows=2, cols=3)
    table.cell(0, 0).text = "项目"
    table.cell(0, 1).text = "金额"
    table.cell(0, 2).text = "备注"
    table.cell(1, 0).text = "A方案"
    table.cell(1, 1).text = "1000"
    table.cell(1, 2).text = "已完成"
    doc.save(path)
    print("docx ok:", path)


def gen_pptx(path):
    from pptx import Presentation
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = "doc-extract 测试演示"
    slide.placeholders[1].text = "第一页要点列表\n要点一\n要点二"
    prs.save(path)
    print("pptx ok:", path)


if __name__ == "__main__":
    root = OUT_DIR
    gen_pdf(os.path.join(root, "doc_extract_sample.pdf"))
    gen_docx(os.path.join(root, "doc_extract_sample.docx"))
    gen_pptx(os.path.join(root, "doc_extract_sample.pptx"))