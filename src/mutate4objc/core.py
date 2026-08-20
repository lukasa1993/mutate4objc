from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Token:
    value: str
    kind: str
    line: int
    column: int
    start: int
    end: int


MULTI = (
    "<<=", ">>=", "...", "===", "!==", "->*", "::", "++", "--", "->",
    "&&", "||", "==", "!=", "<=", ">=", "+=", "-=", "*=", "/=", "%=",
    "&=", "|=", "^=", "<<", ">>", "##",
)


def tokenize(text: str) -> list[Token]:
    tokens: list[Token] = []
    index = 0
    line = 1
    column = 1
    length = len(text)

    def advance(fragment: str) -> None:
        nonlocal line, column
        newlines = fragment.count("\n")
        if newlines:
            line += newlines
            column = len(fragment.rsplit("\n", 1)[-1]) + 1
        else:
            column += len(fragment)

    while index < length:
        start = index
        start_line = line
        start_column = column
        character = text[index]
        if character.isspace():
            index += 1
            while index < length and text[index].isspace():
                index += 1
            advance(text[start:index])
            continue
        if text.startswith("//", index):
            index = text.find("\n", index)
            if index < 0:
                break
            advance(text[start:index])
            continue
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            index = length if end < 0 else end + 2
            advance(text[start:index])
            continue
        if character in {'"', "'"} or (character == "@" and index + 1 < length and text[index + 1] == '"'):
            quote_index = index + 1 if character == "@" else index
            quote = text[quote_index]
            index = quote_index + 1
            escaped = False
            while index < length:
                current = text[index]
                index += 1
                if escaped:
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif current == quote:
                    break
            fragment = text[start:index]
            tokens.append(Token(fragment, "string", start_line, start_column, start, index))
            advance(fragment)
            continue
        if character.isalpha() or character == "_":
            index += 1
            while index < length and (text[index].isalnum() or text[index] == "_"):
                index += 1
            fragment = text[start:index]
            tokens.append(Token(fragment, "identifier", start_line, start_column, start, index))
            advance(fragment)
            continue
        if character.isdigit():
            index += 1
            while index < length and (text[index].isalnum() or text[index] in "._"):
                index += 1
            fragment = text[start:index]
            tokens.append(Token(fragment, "number", start_line, start_column, start, index))
            advance(fragment)
            continue
        operator = next((value for value in MULTI if text.startswith(value, index)), character)
        index += len(operator)
        tokens.append(Token(operator, "operator", start_line, start_column, start, index))
        advance(operator)
    return tokens


import os
from pathlib import Path
from typing import Sequence

EXCLUDED_DIRS = {".git", ".hg", ".build", "build", "DerivedData", "Pods", "target", "vendor"}


def discover_files(root: Path, filters: Sequence[str] = ()) -> list[Path]:
    files: list[Path] = []
    for directory, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if name not in EXCLUDED_DIRS and not name.lower().startswith("test"))
        for filename in sorted(filenames):
            if not filename.endswith((".m", ".mm")):
                continue
            path = Path(directory, filename)
            relative = path.relative_to(root).as_posix()
            if filters and not any(fragment in relative for fragment in filters):
                continue
            files.append(path)
    return files


import json
import subprocess
from dataclasses import asdict, dataclass
from typing import Iterable

REPLACEMENTS = {
    "==": "!=", "!=": "==", ">": "<=", "<": ">=", ">=": "<", "<=": ">",
    "&&": "||", "||": "&&", "YES": "NO", "NO": "YES", "true": "false", "false": "true",
    "+": "-", "-": "+",
}


@dataclass(frozen=True)
class Mutation:
    id: int
    file: str
    line: int
    column: int
    original: str
    replacement: str
    start: int
    end: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class Result:
    mutation: Mutation
    status: str
    exit_code: int | None

    def to_dict(self) -> dict[str, object]:
        return {**self.mutation.to_dict(), "status": self.status, "exit_code": self.exit_code}


def enumerate_mutations(path: Path, root: Path, start_id: int = 1) -> list[Mutation]:
    text = path.read_text(encoding="utf-8")
    out: list[Mutation] = []
    for token in tokenize(text):
        replacement = REPLACEMENTS.get(token.value)
        if replacement is None:
            continue
        out.append(Mutation(start_id + len(out), path.relative_to(root).as_posix(), token.line, token.column, token.value, replacement, token.start, token.end))
    return out


def collect_mutations(root: Path, filters: Sequence[str] = ()) -> list[Mutation]:
    out: list[Mutation] = []
    for path in discover_files(root, filters):
        out.extend(enumerate_mutations(path, root, len(out) + 1))
    return out


def run_mutations(root: Path, mutations: Iterable[Mutation], command: str, timeout: float, max_mutants: int | None = None) -> list[Result]:
    results: list[Result] = []
    for mutation in mutations:
        if max_mutants is not None and len(results) >= max_mutants:
            break
        path = root / mutation.file
        original_text = path.read_text(encoding="utf-8")
        path.write_text(original_text[:mutation.start] + mutation.replacement + original_text[mutation.end:], encoding="utf-8")
        try:
            try:
                completed = subprocess.run(command, cwd=root, shell=True, timeout=timeout, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                results.append(Result(mutation, "survived" if completed.returncode == 0 else "killed", completed.returncode))
            except subprocess.TimeoutExpired:
                results.append(Result(mutation, "timeout", None))
        finally:
            path.write_text(original_text, encoding="utf-8")
    return results


def run_baseline(root: Path, command: str, timeout: float) -> None:
    completed = subprocess.run(command, cwd=root, shell=True, timeout=timeout, check=False)
    if completed.returncode:
        raise RuntimeError(f"baseline tests failed with status {completed.returncode}")


def write_manifest(path: Path, results: Iterable[Result]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([result.to_dict() for result in results], indent=2, sort_keys=True) + "\n", encoding="utf-8")
