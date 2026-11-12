# Known Limitations & Technical Debt

**Version:** 0.8.0  
**Updated:** 2026-11-09  

---

## 1. Architectural Limitations
1. **OS-Level Isolation:** Current sandbox abstraction relies on local Python process execution or Docker if Docker daemon is available. On Windows environments without Docker daemon running, execution runs within the local boundary guarded by Python security policies.
2. **Package Graph Resolution:** `CodeGraph` relies on AST parsing rather than full language servers (LSP). Dynamic imports (e.g. `importlib.import_module()`) and monkey-patching cannot be statically resolved.
3. **Multi-File Refactoring Scope:** While single-file and bounded multi-file patches are fully supported, large-scale cross-repository refactors spanning hundreds of files require chunked execution DAGs.

---

## 2. Security Boundaries & Assumptions
1. **Symlink Support:** While the code strictly defends against symlink escapes, running within git worktrees on filesystems with restricted symlink privileges (e.g. non-admin Windows) defaults to regular file operations.
2. **Model Non-Determinism:** LLM advisory responses can vary across model providers. Deterministic fallback engines ensure critical lifecycle operations succeed even when external APIs fail.

---

## 3. Performance & Resource Bounds
1. **Repository File Cap:** Standard repository intelligence indexes up to 500 source files per inspection pass to avoid memory exhaustion on multi-gigabyte repositories.
2. **Diff Stream Limit:** Command runner truncates stdout/stderr at 32 KiB to prevent buffer blowouts.
3. **Execution Timeout:** All tool invocations and commands enforce a bounded timeout (max 60 seconds).
