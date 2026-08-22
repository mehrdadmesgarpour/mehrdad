#!/usr/bin/env python3
"""Convert LaTeX source (text, equations, images) into a Word .docx file.

The conversion itself is done by Pandoc, which turns LaTeX math into
native, editable Word equations (OMML) and embeds referenced images
into the document. This script adds the plumbing Pandoc does not do
for you:

* locate images referenced with ``\\includegraphics`` — honouring
  ``\\graphicspath`` and extension-less names — across one or more
  search directories
* convert PDF/EPS figures to PNG so Word can actually display them
  (uses pdftoppm, ImageMagick, or Ghostscript — whichever is installed)
* accept a ``.tex`` file, a LaTeX string, or stdin
* optional bibliography processing and a reference .docx for styling

The only required dependency bundles the pandoc binary::

    pip install pypandoc-binary

Command-line usage::

    python latex_to_docx.py paper.tex -o paper.docx
    python latex_to_docx.py --string '$E = mc^2$' -o equation.docx
    cat paper.tex | python latex_to_docx.py - -o paper.docx

Library usage::

    from latex_to_docx import convert_file, convert_string

    convert_file("paper.tex", "paper.docx")
    convert_string(r"\\[ \\nabla \\cdot \\mathbf{u} = 0 \\]", "eq.docx")
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

__all__ = ["convert_file", "convert_string", "main"]

# Extensions tried, in order, when \includegraphics gives no extension.
_TRY_EXTS = [".png", ".jpg", ".jpeg", ".pdf", ".eps", ".gif", ".bmp",
             ".tif", ".tiff", ".svg"]

# Formats Word cannot display; converted to PNG when a tool is available.
_NEEDS_CONVERSION = {".pdf", ".eps"}

_INCLUDEGRAPHICS_RE = re.compile(
    r"(\\includegraphics\s*(?:\[[^\]]*\])?\s*\{)\s*([^}]+?)\s*(\})")
_GRAPHICSPATH_RE = re.compile(r"\\graphicspath\s*\{((?:\s*\{[^}]*\}\s*)+)\}")


def _find_pandoc() -> str:
    """Return the pandoc executable, preferring the pypandoc-bundled one."""
    try:
        import pypandoc  # type: ignore
        return pypandoc.get_pandoc_path()
    except Exception:
        pass
    exe = shutil.which("pandoc")
    if exe:
        return exe
    raise RuntimeError(
        "pandoc not found. Install it with:\n"
        "    pip install pypandoc-binary\n"
        "or install pandoc system-wide from https://pandoc.org")


def _in_comment(source: str, pos: int) -> bool:
    """True if position ``pos`` lies after an unescaped % on its line."""
    line_start = source.rfind("\n", 0, pos) + 1
    segment = source[line_start:pos]
    return bool(re.search(r"(?<!\\)%", segment))


def _graphicspath_dirs(source: str, base_dir: Path) -> list[Path]:
    dirs: list[Path] = []
    for match in _GRAPHICSPATH_RE.finditer(source):
        for entry in re.findall(r"\{([^}]*)\}", match.group(1)):
            entry = entry.strip()
            if entry:
                dirs.append((base_dir / entry) if not Path(entry).is_absolute()
                            else Path(entry))
    return dirs


def _resolve_image(name: str, search_dirs: list[Path]) -> Path | None:
    """Find the file behind an \\includegraphics argument."""
    candidates = [name]
    if Path(name).suffix.lower() not in _TRY_EXTS:
        candidates += [name + ext for ext in _TRY_EXTS]
    for candidate in candidates:
        path = Path(candidate)
        if path.is_absolute():
            if path.is_file():
                return path
            continue
        for directory in search_dirs:
            hit = directory / candidate
            if hit.is_file():
                return hit
    return None


def _to_png(src: Path, out_dir: Path, dpi: int) -> Path | None:
    """Rasterise a PDF/EPS figure to PNG using whatever tool exists."""
    dst = out_dir / (src.stem + ".png")
    n = 1
    while dst.exists():  # same stem from a different directory
        n += 1
        dst = out_dir / f"{src.stem}-{n}.png"

    suffix = src.suffix.lower()
    attempts: list[list[str]] = []
    if suffix == ".pdf" and shutil.which("pdftoppm"):
        attempts.append(["pdftoppm", "-png", "-r", str(dpi), "-singlefile",
                         "-f", "1", "-l", "1", str(src),
                         str(dst.with_suffix(""))])
    magick = shutil.which("magick") or shutil.which("convert")
    if magick:
        attempts.append([magick, "-density", str(dpi), f"{src}[0]",
                         "-background", "white", "-alpha", "remove",
                         str(dst)])
    if shutil.which("gs"):
        cmd = ["gs", "-dSAFER", "-dBATCH", "-dNOPAUSE", f"-r{dpi}",
               "-sDEVICE=png16m", "-dFirstPage=1", "-dLastPage=1",
               "-o", str(dst), str(src)]
        if suffix == ".eps":
            cmd.insert(1, "-dEPSCrop")
        attempts.append(cmd)

    for cmd in attempts:
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except (OSError, subprocess.CalledProcessError):
            continue
        if dst.is_file():
            return dst
    return None


def _prepare_tex(source: str, base_dir: Path, resource_dirs: list[Path],
                 work_dir: Path, dpi: int) -> str:
    """Rewrite \\includegraphics arguments to resolved, Word-friendly files."""
    search_dirs = [base_dir, *resource_dirs,
                   *_graphicspath_dirs(source, base_dir)]
    converted: dict[Path, Path] = {}

    def replace(match: re.Match) -> str:
        if _in_comment(source, match.start()):
            return match.group(0)
        name = match.group(2).strip()
        resolved = _resolve_image(name, search_dirs)
        if resolved is None:
            print(f"warning: image not found: {name}", file=sys.stderr)
            return match.group(0)
        resolved = resolved.resolve()
        if resolved.suffix.lower() in _NEEDS_CONVERSION:
            if resolved not in converted:
                png = _to_png(resolved, work_dir, dpi)
                if png is None:
                    print(f"warning: could not convert {resolved.name} to "
                          "PNG (install poppler-utils, ImageMagick, or "
                          "Ghostscript); Word may not display it",
                          file=sys.stderr)
                    png = resolved
                converted[resolved] = png
            resolved = converted[resolved]
        return match.group(1) + resolved.as_posix() + match.group(3)

    return _INCLUDEGRAPHICS_RE.sub(replace, source)


def _run_pandoc(source: str, base_dir: Path, output: Path,
                resource_dirs: list[Path], reference_doc: Path | None,
                bibliography: Path | None, csl: Path | None,
                number_sections: bool, dpi: int,
                extra_args: list[str]) -> Path:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="latex2docx-") as tmp:
        work_dir = Path(tmp)
        prepared = _prepare_tex(source, base_dir, resource_dirs,
                                work_dir, dpi)
        tex_file = work_dir / "input.tex"
        tex_file.write_text(prepared, encoding="utf-8")

        cmd = [_find_pandoc(), str(tex_file),
               "-f", "latex", "-t", "docx", "-o", str(output),
               "--resource-path",
               os.pathsep.join(str(d) for d in
                               [base_dir, *resource_dirs, work_dir])]
        if reference_doc:
            cmd += ["--reference-doc", str(Path(reference_doc).resolve())]
        if number_sections:
            cmd += ["--number-sections"]
        if bibliography:
            cmd += ["--citeproc", "--bibliography",
                    str(Path(bibliography).resolve())]
        if csl:
            cmd += ["--csl", str(Path(csl).resolve())]
        cmd += extra_args

        # cwd = base_dir so that relative \input{...} keeps working
        result = subprocess.run(cmd, cwd=base_dir)
        if result.returncode != 0:
            raise RuntimeError(f"pandoc failed with exit code "
                               f"{result.returncode}")
    return output


def convert_string(source: str, output: str | Path, *,
                   base_dir: str | Path = ".",
                   resource_dirs: list[str | Path] | None = None,
                   reference_doc: str | Path | None = None,
                   bibliography: str | Path | None = None,
                   csl: str | Path | None = None,
                   number_sections: bool = False,
                   dpi: int = 300,
                   extra_args: list[str] | None = None) -> Path:
    """Convert a LaTeX string to ``output`` (.docx). Returns the path.

    ``source`` may be a full document or just a fragment — pandoc accepts
    body-only LaTeX (e.g. a lone equation) without a preamble.
    Relative image paths are resolved against ``base_dir`` and any
    ``resource_dirs``.
    """
    return _run_pandoc(
        source,
        Path(base_dir).resolve(),
        Path(output),
        [Path(d).resolve() for d in (resource_dirs or [])],
        Path(reference_doc) if reference_doc else None,
        Path(bibliography) if bibliography else None,
        Path(csl) if csl else None,
        number_sections, dpi, list(extra_args or []))


def convert_file(tex_path: str | Path, output: str | Path | None = None,
                 **kwargs) -> Path:
    """Convert a ``.tex`` file to .docx. Returns the output path.

    ``output`` defaults to the input name with a .docx extension.
    Accepts the same keyword options as :func:`convert_string`.
    """
    tex_path = Path(tex_path).resolve()
    try:
        source = tex_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        source = tex_path.read_text(encoding="latin-1")
    if output is None:
        output = tex_path.with_suffix(".docx")
    kwargs.setdefault("base_dir", tex_path.parent)
    return convert_string(source, output, **kwargs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert LaTeX (text, equations, images) to .docx "
                    "using pandoc.",
        epilog="Examples:\n"
               "  %(prog)s paper.tex -o paper.docx\n"
               "  %(prog)s --string '$E=mc^2$' -o equation.docx\n"
               "  cat paper.tex | %(prog)s - -o paper.docx",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", nargs="?",
                        help="input .tex file, or '-' to read from stdin")
    parser.add_argument("--string", metavar="LATEX",
                        help="LaTeX source given directly on the command "
                             "line instead of a file")
    parser.add_argument("-o", "--output", metavar="FILE.docx",
                        help="output path (default: input name with .docx, "
                             "or output.docx for --string/stdin)")
    parser.add_argument("--resource-dir", action="append", default=[],
                        metavar="DIR",
                        help="extra directory to search for images "
                             "(repeatable)")
    parser.add_argument("--reference-doc", metavar="FILE.docx",
                        help="a .docx whose styles (fonts, margins, "
                             "headings) the output should copy")
    parser.add_argument("--bibliography", metavar="FILE.bib",
                        help="process \\cite commands with this "
                             "BibTeX/CSL-JSON file (uses pandoc citeproc)")
    parser.add_argument("--csl", metavar="FILE.csl",
                        help="citation style for --bibliography")
    parser.add_argument("--number-sections", action="store_true",
                        help="number section headings like LaTeX does")
    parser.add_argument("--dpi", type=int, default=300,
                        help="resolution for PDF/EPS figure rasterisation "
                             "(default: 300)")
    parser.add_argument("--pandoc-arg", action="append", default=[],
                        metavar="ARG",
                        help="extra argument passed straight to pandoc "
                             "(repeatable)")
    args = parser.parse_args(argv)

    if bool(args.input) == bool(args.string):
        parser.error("give exactly one input: a .tex file (or '-') "
                     "or --string")

    common = dict(
        resource_dirs=args.resource_dir,
        reference_doc=args.reference_doc,
        bibliography=args.bibliography,
        csl=args.csl,
        number_sections=args.number_sections,
        dpi=args.dpi,
        extra_args=args.pandoc_arg)

    try:
        if args.string is not None:
            out = convert_string(args.string,
                                 args.output or "output.docx", **common)
        elif args.input == "-":
            out = convert_string(sys.stdin.read(),
                                 args.output or "output.docx", **common)
        else:
            out = convert_file(args.input, args.output, **common)
    except (RuntimeError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
