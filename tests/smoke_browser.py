# -*- coding: utf-8 -*-
"""HTML 无头浏览器冒烟（A-5 管线：playwright + 系统 Chrome channel）。

用法：.venv/Scripts/python.exe tests/smoke_browser.py <html路径> <截图目录>
验证：33 个图形 section 是否渲染（每个 section 高度>0）、JS 报错、抽查截图。
"""
import os
import sys
import urllib.parse

from playwright.sync_api import sync_playwright


def file_url(path):
    return "file:///" + urllib.parse.quote(os.path.abspath(path).replace("\\", "/"))


def main(html_path, shot_dir):
    os.makedirs(shot_dir, exist_ok=True)
    errors = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(file_url(html_path), wait_until="networkidle")
        page.wait_for_timeout(600)

        # 逐 section 检查：每个图形 section 可见且非空
        rows = page.evaluate("""
        () => {
          const secs = [...document.querySelectorAll('section, .page, [id^=p]')];
          const out = [];
          for (const s of secs) {
            const r = s.getBoundingClientRect();
            if (r.height > 10) {
              out.push({id: s.id || '(anon)', h: Math.round(r.height),
                        svg: s.querySelectorAll('svg').length,
                        tables: s.querySelectorAll('table').length,
                        text: (s.innerText || '').slice(0, 30).replace(/\\n/g, ' ')});
            }
          }
          return out;
        }""")
        # 兜底：若结构选择器未命中，退回按标题统计
        titles = page.evaluate("""
        () => [...document.querySelectorAll('h1,h2,h3')]
              .map(h => h.innerText.trim()).filter(t => /\\d{2} · /.test(t))""")
        doc_h = page.evaluate("() => document.body.scrollHeight")

        print(f"sections(高度>10): {len(rows)}  标题数(## ·): {len(titles)}  文档总高: {doc_h}px")
        for t in titles:
            print("  title:", t)
        # 抽查 3 张关键图形截图（按标题定位滚动）
        for key, name in [("deployment", "shot_deploy"), ("org_tree", "shot_orgtree"),
                          ("milestone_gantt", "shot_msgantt")]:
            hit = page.evaluate(f"""
            () => {{
              const hs = [...document.querySelectorAll('h1,h2,h3')];
              const h = hs.find(x => x.innerText.includes('{key}'));
              if (h) {{ h.scrollIntoView(); return true; }} return false;
            }}""")
            if hit:
                page.wait_for_timeout(300)
                page.screenshot(path=os.path.join(shot_dir, name + ".png"))
                print(f"screenshot: {name}.png")
        browser.close()

    print("JS 错误:", len(errors))
    for e in errors[:10]:
        print("  [js-error]", e[:160])
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
