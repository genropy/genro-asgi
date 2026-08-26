# Manual checks left by the phases

## Phase 2

- deferred: needs Phase 3 — with a real site behind the front, leave a user
  silent past `user_idle_freeze_minutes` and then click again: he is parked by
  the group while he is silent, and the click wakes him at the destination with
  no 400 and no re-login. DUE NOW: Phase 3 landed the production trigger
  (`GroupHandler.check_user_activity`, on the group's own beat), so the
  silence alone parks him with nobody driving it.

## Phase 4

- deferred: needs a real site behind the front — restart under
  `serve --reload` while a user is clicking, and watch that the click that
  lands during the quit waits and is served after the reboot, with no 400 and
  no re-login. The tests prove the block with a scripted child; only a live
  round proves it against a real drain.
