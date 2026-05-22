# codegraph

Code repository analyzer — produces a call graph and dependency graph for any codebase.

Built on tree-sitter for accurate AST parsing across Python, JavaScript, TypeScript, Java, Go.

## Install

```
npm install -g codegraph
```

## Usage

```
codegraph analyze ./my-repo --format json
codegraph diff main HEAD
```

Pre-commit linter integration and static-analysis tooling for monorepos.
