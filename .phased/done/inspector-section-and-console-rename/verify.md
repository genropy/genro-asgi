# Human checks

## Phase 5
- now — the browser pass an unattended run cannot do: with a running pool
  (`GNR_ASGI_INSPECTOR=1`) open `/_server/inspector/page`, watch a login create
  its user row live, press stop, confirm the view freezes while the pool keeps
  moving, then resume.
