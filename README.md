# mutate4objc

`mutate4objc` performs safe one-at-a-time mutation testing for `.m` and `.mm` files. Its lexer ignores comments and string contents.

## Install

```bash
pipx install git+https://github.com/lukasa1993/mutate4objc.git
```

## Run

```bash
mutate4objc --test-command "make test" --fail-on-survivors
```

Use `--list`, `--max-mutants`, and path fragments to control the run. The tool restores every source file in a `finally` block and writes `target/mutation/mutations.json`.
