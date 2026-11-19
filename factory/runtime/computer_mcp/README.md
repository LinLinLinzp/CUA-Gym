# Harbor computer MCP runtime

Build the two migration candidates from the task sources on Linux.

```bash
python3 factory/pipeline/package.py --runtime computer-mcp \
  --out output/harbor/computer-mcp riverside-showcase-placement exp1-l03
```

Upload the archives from `output/harbor/computer-mcp/tars`. Each archive has
`task.toml` at the root and an adjacent SHA256 file. The packager verifies
Docker `COPY` inputs after projecting the archives to AP's file-only layout.

The task's `computer_mcp` declaration lists the supported desktop applications
and output filenames. Optional `attachments` map site keys to original upload
filenames. The grader reads site state and allowlisted files from the desktop
through a root-only socket. The model receives screenshots and mouse/keyboard
actions through `mcp__desktop__computer`. Oracle replays live under each task's
`solution/solve.py` and use the same computer service.

Run the packaged NOP and GUI Oracle on Harbor 0.1.45 using
`factory/pipeline/platform_check.sh <task-dir>`. Set `HARBOR_BIN` to the path
of the Harbor 0.1.45 executable if it is outside `PATH`.
`factory/pipeline/prescreen.sh` remains an optional model rollout. For a
collected rollout, run `factory/pipeline/audit_computer_mcp.py <trial-dir> <evidence-dir>`
to match the native transcript and ATIF screenshots to the desktop action log.
