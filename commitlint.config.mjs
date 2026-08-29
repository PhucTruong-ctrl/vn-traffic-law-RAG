// Conventional Commits enforcement (mirrors @commitlint/config-conventional v21.2.0).
// Self-contained on purpose: commitlint resolves `extends`/`parserPreset` module
// specifiers from the process CWD, which for the repo-root git hook is this
// directory — where @commitlint/config-conventional is NOT installed (deps live in
// frontend/node_modules). Inlining the rules + parser opts keeps the config
// resolvable from anywhere and immune to node_modules layout changes.
export default {
  parserPreset: {
    parserOpts: {
      headerPattern: /^(\w*)(?:\((.*)\))?!?: (.*)$/,
      breakingHeaderPattern: /^(\w*)(?:\((.*)\))?!: (.*)$/,
      headerCorrespondence: ["type", "scope", "subject"],
      noteKeywords: ["BREAKING CHANGE", "BREAKING-CHANGE"],
      revertPattern: /^(?:Revert|revert:)\s"?([\s\S]+?)"?\s*This reverts commit (\w*)\./i,
      revertCorrespondence: ["header", "hash"],
      issuePrefixes: ["#"],
    },
  },
  ignores: [(message) => message.startsWith("merge:")],
  rules: {
    "body-leading-blank": [1, "always"],
    "body-max-line-length": [2, "always", 100],
    "footer-leading-blank": [1, "always"],
    "footer-max-line-length": [2, "always", 100],
    "header-max-length": [2, "always", 100],
    "header-trim": [2, "always"],
    "subject-case": [
      2,
      "never",
      ["sentence-case", "start-case", "pascal-case", "upper-case"],
    ],
    "subject-empty": [2, "never"],
    "subject-full-stop": [2, "never", "."],
    "type-case": [2, "always", "lower-case"],
    "type-empty": [2, "never"],
    "type-enum": [
      2,
      "always",
      [
        "build",
        "chore",
        "ci",
        "docs",
        "feat",
        "fix",
        "perf",
        "refactor",
        "revert",
        "style",
        "test",
      ],
    ],
  },
};
