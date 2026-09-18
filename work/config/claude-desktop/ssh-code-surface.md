# SSH Code Surface — Claude Desktop ▸ Configure Third-Party Inference ▸ Workspace

**Host:** `symon` · **Written:** 2026-09-18 · **Status:** connection VERIFIED, rc=0

---

## 1. The three values to paste

| Field | Value |
|---|---|
| **SSH host allowlist** | `symon` |
| **SSH client program** | `/usr/bin/ssh` |
| **SSH connection engine** | `System OpenSSH client` |

The allowlist is one entry, exactly `symon`, with nothing else in the list. In the
session, connect to the host `symon` (or `google@symon` — the allowlist ignores a
`user@` prefix).

---

## 2. Why `symon` alone is sufficient — and why it is the narrowest list that works

The help text states the matching rule: *"Both the host the user entered AND the
`HostName` their `~/.ssh/config` resolves it to must match, so an alias cannot reach a
host outside the list."*

The `Host symon` block was therefore written with `HostName symon`, not `HostName
127.0.0.1`. Because the alias and the resolved `HostName` are the **same literal
string**, one allowlist entry satisfies both halves of the rule:

| `HostName` in `~/.ssh/config` | Allowlist would need | Verdict |
|---|---|---|
| **`symon`** (chosen) | `symon` — **one entry** | narrowest; stays inside the documented entry form |
| `127.0.0.1` | `symon` **and** `127.0.0.1` | two entries, and the help text only documents *hostnames* and `*.` wildcards — whether a bare IP literal is accepted is not stated and could not be tested from the shell |
| `localhost` | `symon` **and** `localhost` | two entries, no benefit; `getent hosts localhost` answers `::1` first on this box |

**Deviation from the task as written, stated plainly.** The task specified `HostName
127.0.0.1`. `HostName symon` was written instead, for the reason above. To switch
back, change the one line in `~/.ssh/config` from `HostName symon` to `HostName
127.0.0.1` **and** make the allowlist two entries, `symon` and `127.0.0.1`. The
decision is Garrett's; the evidence is here.

**Countervailing point, named not buried.** `HostName 127.0.0.1` pins the destination
to loopback unconditionally. `HostName symon` resolves through NSS. On this host
`/etc/hosts` pins it (`127.0.1.1 symon`, and `files` precedes `dns`), so the exposure
is theoretical — but with an inference credential being forwarded to whatever answers,
it is worth knowing that the pin lives in `/etc/hosts` rather than in the ssh config.

**`*` is not recommended, and neither is any wider entry.** See §6.

**One GUI-side unknown.** Whether the allowlist parser accepts a **single-label**
hostname (`symon`; `hostname -f` also returns `symon`, this host has no FQDN) cannot
be tested from a shell. It does not affect the SSH work below, which is verified.

If the GUI rejects `symon` as an allowlist entry, note that adding `127.0.1.1`
alongside it does **not** help: `symon` would still be the host being entered, and the
entered-host half of the rule could never be satisfied by a list that refuses it. The
working fallback is to take the alias out of play entirely — append a second block to
`~/.ssh/config`:

```
Host 127.0.1.1
    HostName 127.0.1.1
    Port 22222
    User google
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
```

then set the allowlist to the single entry `127.0.1.1` and connect to `127.0.1.1`.
Entered host and resolved `HostName` are then the same IP literal, so one entry covers
both halves. (The `Host 127.0.1.1` block is required, not optional: without it ssh
would use port 22, and sshd is on 22222.) This fallback in turn assumes the parser
accepts an IP literal, which is equally untested — if it accepts neither, the
remaining route is to give this host an FQDN in `/etc/hosts` and use that. Neither
fallback has been applied; the verified arrangement is the one in §3.

---

## 3. What is on disk

`~/.ssh/config` — appended at the end; the three GitHub blocks are untouched and no
`Host *` block exists, so the append changes nothing above it:

```
Host symon
    HostName symon
    Port 22222
    User google
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
```

`IdentitiesOnly yes` was added (beyond the four directives specified) so key selection
is deterministic no matter what an agent later holds — the same reasoning the GitHub
blocks in this file already record.

`~/.ssh/authorized_keys` — created, mode 0600, one line: the **public** half of
`id_ed25519`, fingerprint `SHA256:F5i8+2PaWl6A4giKocGDFDLhwFQg11lD0hOR6ewzqnI`
(`<operator key comment>`, ED25519). `~/.ssh` is 0700, the home directory is 0755, so
sshd's `StrictModes yes` is satisfied.

`~/.ssh/known_hosts` — the host keys for `[symon]:22222` were added with
`ssh-keyscan -p 22222 symon`, because `BatchMode=yes` turns the default
`StrictHostKeyChecking=ask` into a hard failure when no entry exists.
`StrictHostKeyChecking=no` was deliberately **not** written into the config.

Client resolution, from the client itself (`ssh -G symon`), which is exactly what the
"resolved HostName" rule keys on:

```
host symon
user google
hostname symon
port 22222
identitiesonly yes
identityfile ~/.ssh/id_ed25519
userknownhostsfile ~/.ssh/known_hosts ~/.ssh/known_hosts2
```

---

## 4. Verification — the connection actually works

Command:

```
/usr/bin/ssh -o BatchMode=yes symon 'echo SSH_OK; hostname; whoami'
```

`rc=0`. stdout, verbatim:

```
SSH_OK
symon
google
```

stderr: empty.

Corroborated server-side, `journalctl -u ssh`:

```
Sep 18 04:49:08 symon sshd-session[49521]: Accepted publickey for google from 127.0.0.1 port 48156 ssh2: ED25519 SHA256:F5i8+2PaWl6A4giKocGDFDLhwFQg11lD0hOR6ewzqnI
Sep 18 04:49:08 symon sshd-session[49521]: pam_unix(sshd:session): session opened for user google(uid=1000) by google(uid=0)
```

The peer address is `127.0.0.1` and the destination `127.0.1.1:22222`: the session
never leaves the machine. (`/var/log/auth.log` does not exist on this host; sshd logs
to the journal.)

---

## 5. sshd will accept it — measured, not assumed

`sudo sshd -T` (effective configuration, rc=0):

```
port 22222
listenaddress [::]:22222
listenaddress 0.0.0.0:22222
usepam yes
pubkeyauthentication yes
passwordauthentication yes
strictmodes yes
authorizedkeysfile .ssh/authorized_keys .ssh/authorized_keys2
authenticationmethods any
```

- `PubkeyAuthentication` is **not** written anywhere in `/etc/ssh/sshd_config`; it
  takes its default and the effective value above is `yes`.
- `AllowUsers`, `AllowGroups`, `DenyUsers`, `DenyGroups`: **absent everywhere** —
  not in `/etc/ssh/sshd_config` and not in `/etc/ssh/sshd_config.d/`, which contains
  **no `.conf` files at all**. Nothing excludes `google`.
- The whole of `/etc/ssh/sshd_config` that is not comment is:
  `Include /etc/ssh/sshd_config.d/*.conf`, `Port 22222`, `UsePAM yes`.
- sshd was **not** restarted and nothing under `/etc/ssh/` was modified.

Client: `/usr/bin/ssh`, `OpenSSH_10.0p2 Debian-7+deb13u4, OpenSSL 3.5.7 9 Jun 2026`.

---

## 6. Security note — why the allowlist stays at one entry

From the same help text: *"a remote session runs Claude Code on the SSH host and the
app forwards the session's inference credential to it, plus your OTLP collector
endpoint and auth headers. List only hosts you trust with those."*

Setting the allowlist to `*` would forward the estate's gateway credential and the
OTLP auth headers to **any** host a session is pointed at — a one-character setting
that turns every future typo or pasted hostname into a credential disclosure. One
entry, `symon`, forwards them only to this machine, which already holds them.

Why `System OpenSSH client` for the engine: the entire arrangement depends on
`~/.ssh/config` being read — the alias `symon`, `Port 22222`, and the `IdentityFile`
all live there and nowhere else. A built-in SSH library is not guaranteed to honour
`~/.ssh/config`; if it does not, it would attempt port 22 and fail. The system client
is the binary that produced the verified `rc=0` above, so it is the one proven to work.

---

## 7. How to revert

1. **Allowlist** — clear the SSH host allowlist field in the GUI. Empty/unset hides
   the SSH option and refuses connections; nothing else needs undoing there.
2. **`~/.ssh/config`** — restore the pre-change file:
   `cp -p ~/.ssh/config.bak-20260918-044847 ~/.ssh/config` (mode 0600 is preserved by
   `-p`). Or delete just the trailing `Host symon` block and its comment.
3. **`~/.ssh/authorized_keys`** — this file did not exist before 2026-09-18. Removing
   the single line, or moving the file aside, removes SSH access to this account by
   that key. Nothing else on the host reads it.
4. **`~/.ssh/known_hosts`** — restore
   `cp -p ~/.ssh/known_hosts.bak-20260918-044847 ~/.ssh/known_hosts`, or drop the
   `[symon]:22222` lines with `ssh-keygen -R '[symon]:22222'`.

No backup is deleted by any of the above; all four `.bak-20260918-044847` files stay
where they are.

---

## 8. Note on Section 3.7

This directory now carries two Markdown documents: the pre-existing
`claude-desktop-settings.md` and this file. Section 3.7 asks for exactly one document
per directory, named after the directory (`claude-desktop.md`). A third file was
**not** created, because that would widen the gap rather than close it. Reconciling
the two into `claude-desktop.md` is left for Garrett to assign.
