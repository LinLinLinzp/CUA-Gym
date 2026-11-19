# Harbor computer MCP runtime

Build the two migration candidates from the task sources on Linux with Python 3.12.

```bash
python3 factory/pipeline/package.py --runtime computer-mcp \
  --out output/harbor/computer-mcp riverside-showcase-placement exp1-l03
```

Upload the archives from `output/harbor/computer-mcp/tars`. Each archive has
`task.toml` at the root and an adjacent SHA256 file. Before the packager
publishes the archive, it checks that `task.toml` ends with
`[[environment.mcp_servers]]` followed by `[environment]`, the agent timeout
is 18,000 seconds, and Claude Code
loads the desktop MCP endpoint declared in `task.toml`. The shared verifier
uses the snapshot socket on Harbor 0.1.45. The packager also checks
Docker `COPY` inputs in AP's file-only layout, adding a `.gitkeep` when
the desktop workspace input would otherwise be empty.

The D11 release check requires all eight checkpoint fields in
`verifier-checkpoints.md`. Every fixture runs the packaged verifier, and each
`report.json` must contain each rubric checkpoint ID exactly once. A failed
check stops publication of that archive.

The task's `computer_mcp` declaration lists the supported desktop applications
and output filenames. Optional `attachments` map site keys to original upload
filenames. The grader reads site state and allowlisted files from the desktop
through a root-only socket. The model receives screenshots and mouse/keyboard
actions through `mcp__desktop__computer`. Oracle replays live under each task's
`solution/solve.py` and use the same computer service. The desktop health
check requests a real snapshot and reads its size header. The verifier
extracts the snapshot and checks it before scoring.

The task Dockerfiles use Aliyun APT and PyPI mirrors and npmmirror for the
pinned Claude Code archive. AP's outer WebIDE has its own APT configuration.

Run the packaged NOP and GUI Oracle on Harbor 0.1.45 using
`factory/pipeline/platform_check.sh <task-dir>`. Set `HARBOR_BIN` to the path
of the Harbor 0.1.45 executable if it is outside `PATH`.
The check verifies the upload archive's SHA256, extracts only its files
into a clean directory, and runs both trials from that directory. It also
matches both Harbor reports to the published checkpoint list.
`factory/pipeline/prescreen.sh` remains an optional model rollout. For a
collected rollout, run `factory/pipeline/audit_computer_mcp.py <trial-dir> <evidence-dir>`
to match the native transcript and ATIF screenshots to the desktop action log.
