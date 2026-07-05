"""Static CodeGraph builder for the VN2024 pipeline.

The CodeGraph is a lightweight, dependency-free inventory of the repository's
Python code.  It records modules, top-level classes/functions, imports, and
intra-repository call edges so maintainers can answer questions such as "what
calls run_mapping?" or "which pipeline stage imports settings?" without loading
large data files or executing the pipeline.
"""
from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class CodeNode:
    """A graph node representing a module, class, or function."""

    id: str
    kind: str
    path: str
    lineno: int = 1
    name: str = ""


@dataclass(frozen=True)
class CodeEdge:
    """A directed relationship between two graph nodes."""

    source: str
    target: str
    kind: str
    lineno: int = 1
    symbol: str = ""


@dataclass
class CodeGraph:
    """Static graph of this repository's Python modules and relationships.

    Build with :meth:`from_repo`, then serialize with :meth:`to_json`,
    :meth:`to_markdown`, or :meth:`to_dot`.
    """

    root: str
    nodes: dict[str, CodeNode] = field(default_factory=dict)
    edges: list[CodeEdge] = field(default_factory=list)

    @classmethod
    def from_repo(
        cls,
        root: str | Path,
        *,
        include: Iterable[str] = ("*.py",),
        exclude_dirs: Iterable[str] = (".git", "__pycache__", ".pytest_cache"),
    ) -> "CodeGraph":
        root_path = Path(root).resolve()
        graph = cls(root=str(root_path))
        py_files: list[Path] = []
        excluded = set(exclude_dirs)
        for pattern in include:
            for path in root_path.rglob(pattern):
                if any(part in excluded for part in path.parts):
                    continue
                py_files.append(path)
        for path in sorted(set(py_files)):
            graph._add_file(path, root_path)
        graph._add_call_edges(root_path)
        return graph

    def _add_file(self, path: Path, root: Path) -> None:
        rel = path.relative_to(root).as_posix()
        module_id = _module_id(path, root)
        self.nodes[module_id] = CodeNode(module_id, "module", rel, 1, module_id)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        except SyntaxError as exc:
            self.edges.append(CodeEdge(module_id, module_id, "parse_error", exc.lineno or 1, str(exc)))
            return

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn_id = f"{module_id}.{node.name}"
                self.nodes[fn_id] = CodeNode(fn_id, "function", rel, node.lineno, node.name)
                self.edges.append(CodeEdge(module_id, fn_id, "defines", node.lineno, node.name))
            elif isinstance(node, ast.ClassDef):
                class_id = f"{module_id}.{node.name}"
                self.nodes[class_id] = CodeNode(class_id, "class", rel, node.lineno, node.name)
                self.edges.append(CodeEdge(module_id, class_id, "defines", node.lineno, node.name))
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        meth_id = f"{class_id}.{child.name}"
                        self.nodes[meth_id] = CodeNode(meth_id, "method", rel, child.lineno, child.name)
                        self.edges.append(CodeEdge(class_id, meth_id, "defines", child.lineno, child.name))
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for imported in _import_names(node):
                    self.edges.append(CodeEdge(module_id, imported, "imports", node.lineno, imported))

    def _add_call_edges(self, root: Path) -> None:
        local_symbols = {node.name: node.id for node in self.nodes.values() if node.kind in {"function", "class"} and node.name}
        for node in list(self.nodes.values()):
            if node.kind != "module":
                continue
            path = root / node.path
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=node.path)
            except SyntaxError:
                continue
            scope_stack: list[str] = [node.id]
            visitor = _CallVisitor(self, local_symbols, scope_stack)
            visitor.visit(tree)

    def to_dict(self) -> dict:
        return {
            "root": self.root,
            "nodes": [asdict(n) for n in sorted(self.nodes.values(), key=lambda n: n.id)],
            "edges": [asdict(e) for e in sorted(self.edges, key=lambda e: (e.source, e.kind, e.target, e.lineno))],
        }

    def to_json(self, **kwargs) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True, **kwargs)

    def to_dot(self) -> str:
        lines = ["digraph CodeGraph {"]
        for node in sorted(self.nodes.values(), key=lambda n: n.id):
            lines.append(f'  "{node.id}" [label="{node.name or node.id}\\n{node.kind}"];')
        for edge in self.edges:
            if edge.kind in {"defines", "calls"}:
                lines.append(f'  "{edge.source}" -> "{edge.target}" [label="{edge.kind}"];')
        lines.append("}")
        return "\n".join(lines)

    def to_markdown(self) -> str:
        by_path: dict[str, list[CodeNode]] = {}
        for node in self.nodes.values():
            by_path.setdefault(node.path, []).append(node)
        lines = ["# CodeGraph", "", f"Root: `{self.root}`", ""]
        for path in sorted(by_path):
            lines.append(f"## `{path}`")
            for node in sorted(by_path[path], key=lambda n: (n.lineno, n.id)):
                if node.kind == "module":
                    continue
                lines.append(f"- `{node.id}` ({node.kind}, line {node.lineno})")
            lines.append("")
        lines.append("## Edges")
        for edge in sorted(self.edges, key=lambda e: (e.kind, e.source, e.target)):
            lines.append(f"- `{edge.source}` --{edge.kind}--> `{edge.target}`")
        return "\n".join(lines)


def _module_id(path: Path, root: Path) -> str:
    rel = path.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _import_names(node: ast.Import | ast.ImportFrom) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    base = "." * node.level + (node.module or "")
    return [f"{base}.{alias.name}".strip(".") for alias in node.names]


class _CallVisitor(ast.NodeVisitor):
    def __init__(self, graph: CodeGraph, local_symbols: dict[str, str], scope_stack: list[str]):
        self.graph = graph
        self.local_symbols = local_symbols
        self.scope_stack = scope_stack

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._with_scope(node.name, node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._with_scope(node.name, node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._with_scope(node.name, node)

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node.func)
        if name:
            target = self.local_symbols.get(name.split(".")[-1])
            if target:
                self.graph.edges.append(CodeEdge(self.scope_stack[-1], target, "calls", node.lineno, name))
        self.generic_visit(node)

    def _with_scope(self, name: str, node: ast.AST) -> None:
        parent = self.scope_stack[-1]
        scope = f"{parent}.{name}"
        if scope not in self.graph.nodes:
            scope = parent
        self.scope_stack.append(scope)
        self.generic_visit(node)
        self.scope_stack.pop()


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""
