# Purpose

You are implementing the plan in IMPLEMENTATION.md.

The Mac Mini and NUC-1 should be complete.

NUC-2, NUC-3 and testing remain.

You can SSH to each host (m1-mini.local, nuc-1.local, nuc-2.local and nuc-3.local).

You can use the auth information (you should just need SSH_PASSWORD) by loading our config from SOPS secrets:

`sops exec-env secrets.env <command> [ARGUMENTS]` - SSH_PASSWORD will be populated into memory.

Please begin implementation. As needed, create or update IMPLEMENTATION_ADDENDUM.md to track our work and our changes.
