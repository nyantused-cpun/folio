# -*- coding: utf-8 -*-
"""C-A8 回归：review 命令帮助文案不得宣称不可审的二进制格式（0907 计划 W1）。

历史缺陷：help 宣称「HTML/PPT/DOCX」，但 review 仅支持 HTML 文本提取，
PPT/DOCX 二进制不可审——承诺失效。默认修法=撤文案。
"""

from _cli import build_parser


def test_review_help_does_not_claim_ppt_docx_support():
    parser = build_parser()
    sub = [a for a in parser._actions if hasattr(a, "choices") and a.choices][0]
    review_parser = sub.choices["review"]
    output_file_action = next(a for a in review_parser._actions
                              if a.dest == "output_file")
    help_text = output_file_action.help or ""
    assert "HTML" in help_text
    assert "PPT/DOCX" not in help_text or "待实装" in help_text, (
        f"review help 提及 PPT/DOCX 必须带「待实装」限定（现文案：{help_text}）")
