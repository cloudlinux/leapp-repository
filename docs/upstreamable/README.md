# Upstreamable changes

Changes in this fork that are not CloudLinux-specific and should be offered
upstream. Anything touching `repos/system_upgrade/common/` is a candidate:
that tree is shared with AlmaLinux's fork and, through it, with oamg.

One file per change, named after the actor or library it touches. Each should
say what the upstream bug is, how to reproduce it without CloudLinux, what the
fix does, and whether it has been proposed yet.

Keeping a change here rather than proposing it immediately is fine - the point
is that the next person rebasing the fork can tell a deliberate divergence from
an accident.
