# -*- coding: utf-8 -*-
"""T6 新增 CLI 命令注册测试。"""

import _cli


class TestNewCliCommands:
    def test_parser_registers_commands(self):
        parser = _cli.build_parser()
        for cmd in (
            "query-rewrite", "fact-guard", "guard-audit",
            "bm25-rebuild", "eval-run", "eval-report",
        ):
            # 能 parse 且 command 属性正确即可证明已注册
            args = parser.parse_args([cmd])
            assert args.command == cmd

    def test_dispatch_contains_new_commands(self):
        dispatch = _cli._build_dispatch()
        for cmd in (
            "query-rewrite", "fact-guard", "guard-audit",
            "bm25-rebuild", "eval-run", "eval-report",
        ):
            assert cmd in dispatch