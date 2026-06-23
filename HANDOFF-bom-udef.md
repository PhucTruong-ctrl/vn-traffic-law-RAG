# Handoff: Viết tài liệu + Agent cho dự án Bom UDEF

Dựa trên quy trình đã làm với file `09-giai-thich-he-thong.tex`.

---

## 1. Cài đặt môi trường LaTeX

```bash
# CachyOS / Arch Linux
sudo pacman -S --overwrite='*' \
  texlive-basic texlive-bin texlive-latex texlive-latexrecommended \
  texlive-latexextra texlive-pictures texlive-fontsrecommended \
  texlive-fontsextra texlive-binextra texlive-formatsextra texlive-langother
```

`texlive-langother` chứa `vntex` + `babel-vietnamese` cho tiếng Việt.
`texlive-fontsrecommended` chứa `mathptmx` (font Times cho luận văn).

---

## 2. Cấu trúc file `.tex` chuẩn

```
% !TEX program = pdflatex
\documentclass[a4paper,12pt]{extreport}
\usepackage[T5]{fontenc}    % mã hóa tiếng Việt
\usepackage[utf8]{inputenc}
\usepackage{mathptmx}        % font Times
\usepackage[vietnamese]{babel}
\usepackage[left=3.5cm,right=2cm,top=2cm,bottom=2cm]{geometry}
\usepackage{setspace}\setstretch{1.2}
\usepackage{amsmath,amssymb}
\usepackage{graphicx,float}
\usepackage{listings}        % cho \lstinline
\usepackage[hidelinks]{hyperref}
\begin{document}
% ... nội dung ...
\end{document}
```

---

## 3. Stop-Slop cho tiếng Việt (học thuật)

### Dấu câu bị cấm
| Cấm | Thay bằng |
|------|-----------|
| `---` hoặc ` -- ` | `: ` (dấu hai chấm + space) |
| `$\rightarrow$` | `->` |
| `—`, `–` (Unicode) | `-` |
| `≥`, `≤`, `×` | `$\ge$`, `$\le$`, `$\times$` |

### Từ đệm cần xóa
| Từ đệm | Xử lý |
|--------|-------|
| `thực sự`, `hoàn toàn`, `đơn giản` | Xóa |
| `có thể được` | `được` |
| `đặc biệt là` | Xóa |
| `dựa trên` | `theo` / `từ` |
| `một cách` + adj | Adj trực tiếp |
| `trên cơ sở` | `từ` |

### Giọng bị động (passive voice)
| Bị động | Chủ động |
|---------|----------|
| `được xây dựng` | `xây dựng` |
| `được sử dụng` | `dùng` / `sử dụng` |
| `được thực hiện` | `thực hiện` |
| `có thể được kiểm tra` | `kiểm tra` |

### Meta-commentary (tự giới thiệu) — xóa
- "Phần này giải thích..."
- "Như đã trình bày ở trên..."
- "Chi tiết về X được trình bày ở phần sau"

---

## 4. Pitfalls khi dùng pdflatex + T5 encoding

| Vấn đề | Giải pháp |
|--------|-----------|
| `_` trong `\texttt{}` bị lỗi `Missing $` | Dùng `\textunderscore` trong `\texttt{}`, hoặc `\lstinline!...!` |
| `_` trong `\text{}` (math mode) | Phải là `\_` |
| `_` ngoài math mode | Phải escape: `\_` |
| `&` trong văn bản ngoài table | Phải escape: `\&` |
| `\[` bị hiểu là math display | Dùng `\\[` (double backslash) cho line break |
| `**bold**` (Markdown) không hoạt động | Dùng `\textbf{bold}` |
| Bảng Markdown `\|...\|` không hoạt động | Dùng `\begin{tabular}` |
| `\lstinline!...!` chứa `!` bên trong | Đổi delimiter: `\lstinline@...@` |

### Compile
```bash
cd docs
rm -f *.aux *.log *.out *.toc *.pdf
pdflatex -interaction=nonstopmode -halt-on-error file.tex  # pass 1
pdflatex -interaction=nonstopmode -halt-on-error file.tex  # pass 2 (cross-ref)
pdflatex -interaction=nonstopmode -halt-on-error file.tex  # pass 3 (TOC final)
```

---

## 5. Agent workflow cho review tài liệu

### 5.1 Cấu trúc 3-reviewer pipeline

```
Stop-slop (user) → Hygienic Reviewer → FIX → Second Opinion → FIX → Critical Reviewer → FIX → DONE
```

### 5.2 Load skill stop-slop trước khi review
```python
skill("stop-slop")
```

### 5.3 Gọi reviewer 1: Hygienic
```python
task({
  subagent_type: "hygienic-reviewer",
  description: "Hygienic review of document",
  prompt: """
Review the file `path/to/file.tex` for slop and writing quality.

## Context
Vietnamese academic document. Stop-slop already partially applied:
- No em dashes (---, --)
- No arrow icons ($\rightarrow$ -> ->)
- Filler words partially removed

## Review Categories
1. Vietnamese filler words
2. Passive voice overuse  
3. Sentence rhythm
4. Vagueness
5. Meta-commentary
6. Redundancy

Read the FULL file. Return specific line numbers, original text, and suggested fixes.
Verdict: OKAY or REJECT with action plan.
"""
})
```

### 5.4 Gọi reviewer 2: Second Opinion
```python
task({
  subagent_type: "reviewer-second-opinion",
  description: "Second opinion review",
  prompt: """
Review `path/to/file.tex` after hygienic review fixes.

## Previous fixes applied:
- (list what was fixed)

## Areas to check:
1. Passive voice remaining
2. Argument structure gaps
3. Concrete specificity
4. Academic tone
5. $rightarrow$ replacement
6. LaTeX syntax errors

Challenge assumptions from first review if needed.
Return line numbers with fixes. Verdict: OKAY or REJECT.
"""
})
```

### 5.5 Gọi reviewer 3: Critical (final)
```python
task({
  subagent_type: "reviewer-critical",
  description: "Final critical review",
  prompt: """
FINAL CRITICAL REVIEW of `path/to/file.tex`.

## Context
Vietnamese academic thesis. Has undergone hygienic + second-opinion reviews.
All stop-slop fixes applied.

## Check:
1. Architecture/Security - any security concerns?
2. Technical Accuracy - formulas, algorithms, claims
3. Completeness - any section too brief?
4. Academic Quality - thesis standard?
5. Remaining Slop
6. LaTeX Quality - formatting, commands
7. Cross-references - correct?
8. Figures/Tables - properly formatted?

Read FULL file. Return structured review. Verdict: OKAY or REJECT.
"""
})
```

---

## 6. .gitignore cho dự án LaTeX

```gitignore
# LaTeX aux files
*.aux *.lof *.log *.lot *.out *.toc *.fls *.fdb_latexmk *.synctex.gz

# Python
__pycache__/ *.pyc

# OS
.DS_Store Thumbs.db

# Temp
texput.pdf
```

---

## 7. Checklist trước khi nộp

- [ ] Compile 3 pass không lỗi
- [ ] Không còn `---`, `$\rightarrow$`, `**bold**`
- [ ] Không còn từ đệm ("thực sự", "hoàn toàn", "có thể được")
- [ ] Tất cả `_` trong text mode đã escape (`\_`)
- [ ] Công thức toán trong `\begin{equation}`, không phải text
- [ ] Bảng dùng `\begin{tabular}`, không phải Markdown `|...|`
- [ ] Có `\cite{}` cho mọi `\bibitem`
- [ ] Không có placeholder (`\ldots` thay cho nội dung thật)
- [ ] Đã `git commit` sau mỗi lần fix lớn
- [ ] PDF output ổn định qua các pass
