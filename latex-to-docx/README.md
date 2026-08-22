# LaTeX → DOCX Converter

Convert LaTeX source — **text, equations, and images** — into a Microsoft
Word `.docx` file.

The conversion engine is [Pandoc](https://pandoc.org):

- **Equations** (`$...$`, `\[...\]`, `equation`, `align`, …) become
  **native, editable Word equations** (OMML), not pictures.
- **Text and structure** — sections, bold/italic, lists, tables,
  cross-references, footnotes, title/author — map to Word styles.
- **Images** referenced with `\includegraphics` are found on disk and
  embedded into the `.docx`.

On top of Pandoc, `latex_to_docx.py` adds what Pandoc does not do itself:

- Resolves image paths the way LaTeX does: honours `\graphicspath{...}`,
  tries extensions for extension-less names, searches extra directories
  you pass with `--resource-dir`.
- **Converts PDF/EPS figures to PNG** so Word can actually display them
  (uses `pdftoppm`, ImageMagick, or Ghostscript — whichever is installed).
- Accepts a `.tex` file, a raw LaTeX string, or stdin.
- Optional bibliography processing (`\cite` + a `.bib` file) and a
  reference `.docx` to control the output's fonts/margins/heading styles.

## Installation

```bash
pip install pypandoc-binary
```

That single package bundles the `pandoc` binary — no system install
needed. (If you already have `pandoc` on your PATH, the script uses it
and needs no Python packages at all.)

Optional, only needed if your LaTeX includes **PDF or EPS figures**:
install one of [Poppler](https://poppler.freedesktop.org/) (`pdftoppm`),
[ImageMagick](https://imagemagick.org), or
[Ghostscript](https://www.ghostscript.com):

```bash
# Debian/Ubuntu          # macOS (Homebrew)       # Windows (choco)
sudo apt install poppler-utils   |   brew install poppler   |   choco install poppler
```

## Usage

```bash
# a .tex file → .docx (default output: paper.docx next to the input)
python latex_to_docx.py paper.tex

# choose the output name
python latex_to_docx.py paper.tex -o out/paper.docx

# a LaTeX snippet directly — a full preamble is not required
python latex_to_docx.py --string 'Inline $E=mc^2$ and \[ \nabla \cdot \mathbf{u} = 0 \]' -o eq.docx

# from stdin
cat paper.tex | python latex_to_docx.py - -o paper.docx

# images live somewhere else; number the sections like LaTeX does
python latex_to_docx.py paper.tex --resource-dir ../figures --number-sections

# process citations, and copy styles (fonts, margins) from a template docx
python latex_to_docx.py paper.tex --bibliography refs.bib --csl ieee.csl --reference-doc template.docx
```

All options:

| Option | Meaning |
| --- | --- |
| `-o, --output FILE.docx` | Output path (default: input name with `.docx`) |
| `--string LATEX` | Convert a LaTeX string instead of a file |
| `--resource-dir DIR` | Extra directory to search for images (repeatable) |
| `--reference-doc FILE.docx` | Copy styles from this document |
| `--bibliography FILE.bib` | Resolve `\cite` with this BibTeX/CSL-JSON file |
| `--csl FILE.csl` | Citation style for `--bibliography` |
| `--number-sections` | Number headings (1, 1.1, …) like LaTeX |
| `--dpi N` | Resolution for PDF/EPS rasterisation (default 300) |
| `--pandoc-arg ARG` | Pass an extra argument straight to pandoc (repeatable) |

### As a library

```python
from latex_to_docx import convert_file, convert_string

convert_file("paper.tex", "paper.docx", number_sections=True)

convert_string(
    r"The energy is $E = mc^2$.",
    "note.docx",
    base_dir="figures/",   # where relative image paths resolve from
)
```

## Example

[`examples/sample.tex`](examples/sample.tex) exercises everything — title,
sections, inline/display/aligned equations, an embedded figure with a
caption, lists, and a table:

```bash
cd examples
python make_figure.py                            # generates figure.png (stdlib only)
python ../latex_to_docx.py sample.tex -o sample.docx
```

Open `sample.docx` in Word: the equations are editable Word equations
and the figure is embedded with its caption.

## What converts well, and what doesn't

Works well: standard article-style documents — text formatting, sectioning,
`amsmath` equations, `graphicx` images, tables (`tabular`/`booktabs`),
lists, footnotes, `\label`/`\ref`, hyperlinks, title/author/date.

Limitations to know about:

- **TikZ/PGF pictures are not rendered** (pandoc skips them). Compile them
  to PDF first (e.g. with the `standalone` class) and `\includegraphics`
  the PDF — this tool will then rasterise and embed it.
- Heavy custom macros may be dropped; prefer `\newcommand` definitions in
  the same file (pandoc expands simple ones).
- Exact page layout (floats, two-column, `\vspace`) does not carry over —
  Word gets the content and styles, not LaTeX's typesetting.
- Equation numbering: Word shows equations without LaTeX's automatic
  `(1), (2), …` numbers.
