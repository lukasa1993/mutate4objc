from pathlib import Path

from mutate4objc.core import enumerate_mutations, run_mutations


def test_lexer_ignores_comments_and_strings(tmp_path: Path) -> None:
    source = tmp_path / "sample.m"
    source.write_text('// YES == NO\nNSString *s = @"YES && NO";\nBOOL f(BOOL x) { return x == YES && NO; }\n', encoding="utf-8")
    mutations = enumerate_mutations(source, tmp_path)
    assert [item.original for item in mutations] == ["==", "YES", "&&", "NO"]


def test_restores_source(tmp_path: Path) -> None:
    source = tmp_path / "sample.m"
    original = "BOOL value = YES;\n"
    source.write_text(original, encoding="utf-8")
    mutation = enumerate_mutations(source, tmp_path)[0]
    result = run_mutations(tmp_path, [mutation], "python -c 'raise SystemExit(1)'", 5)[0]
    assert result.status == "killed"
    assert source.read_text(encoding="utf-8") == original
