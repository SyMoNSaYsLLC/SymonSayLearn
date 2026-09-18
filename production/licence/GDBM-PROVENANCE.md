# gdbm 1.26 — provenance census

**Question asked:** is any part of gdbm available from another party on non-copyleft
terms, such that the estate could take that instead?

**Answer: no.** Every file compiled into `libgdbm.so` and `libgdbm_compat.so` carries a
GPL grant held by the Free Software Foundation. The permissive material in the tree is
autotools plumbing and a Bison skeleton — build-time only, never in the image.

The search did surface two things worth recording. Neither unblocks anything.

Audited: `/home/google/Downloads/gdbm-1.26`, 258 regular files, 5.3 MB, nothing modified.

---

## 1. Identity — this tree is what the estate builds

| Check | Value |
|---|---|
| `sha256sum gdbm-1.26.tar.gz` | `6a24504a14de4a744103dcb936be976df6fbe88ccff26065e54c1c47946f4a5e` |
| matches `SRC_URI[sha256sum]` in | `openembedded-core/meta/recipes-support/gdbm/gdbm_1.26.bb` |
| `md5sum COPYING` | `241da1b9fe42e642cbb2c24d5e0c4d24` — matches the recipe's `LIC_FILES_CHKSUM` |
| version | 1.26, released 2025-07-30 |

---

## 2. Finding: the recipe's licence token matches zero files

```
LICENSE = "GPL-3.0-only"
LIC_FILES_CHKSUM = "file://COPYING;md5=241da1b9fe42e642cbb2c24d5e0c4d24"
```

Whole-tree grep over all 258 files:

| Grant found in the file | Files |
|---|---|
| `either version 2, or (at your option) any later version` | **75** |
| `either version 3 ... or (at your option) any later version` | **99** |
| in both sets | **0** — a clean partition |
| version 3 **without** "or later" | **0** |

The only `GPL-3.0-only` text in the tree is `COPYING` itself, which is the licence
document and correctly names version 3 without "or later". **No source file is
GPL-3-only.** The accurate token is `GPL-3.0-or-later & GPL-2.0-or-later`.

**The mechanism that lets this through:** `LIC_FILES_CHKSUM` checksums `COPYING` and
nothing else. It never opens a source header. The boilerplate matches, the build
passes, and the headers are never read.

### The three *installed* public headers are GPL-2-or-later

This is the sharpest contradiction, because these are the files a consumer compiles
against:

| File | Install target | Grant at line 8 |
|---|---|---|
| `src/gdbm.h.in` | `src/Makefile.am:18` `nodist_include_HEADERS = gdbm.h` | version 2 or later |
| `compat/dbm.h` | `compat/Makefile.am:29` `compatinclude_HEADERS` | version 2 or later |
| `compat/ndbm.h` | `compat/Makefile.am:29` `compatinclude_HEADERS` | version 2 or later |

All three: `Copyright (C) 1990-2025 Free Software Foundation, Inc.`

### Why — the incomplete 2007 sweep

`ChangeLog:4733`, entry dated `Sun Oct 28 15:50:53 PDT 2007  Jason Downs`:

```
	* COPYING, all source files: Update to GPLv3.
```

"All source files" was not all source files. Eighteen years later 75 files still carry
the version-2 grant, including all three installed headers.

**This runs the wrong way for us.** "Version 2 or later" is a *broader* grant than
"version 3 only", not a weaker copyleft. It is a documentation defect, not a seam.

---

## 3. The BSD / AT&T descent thesis — disconfirmed

The `ndbm` interface is 1979 AT&T Unix, so `compat/` was the obvious place to look for
absorbed permissive code. It is not there.

| Pattern | Files in tree |
|---|---|
| `Regents of the University` | **0** |
| `AT&T` | **0** |
| `Vern Paxson` | **0** |
| `Berkeley` | 2 — OS-name strings in `config.sub` / `config.guess` |

Every copyright line in all 23 files of `compat/` is the Free Software Foundation
(1990-2025, 1993-2025, 1994-2021, 2007-2025, 2011-2025). `compat/dbmopen.c:1` states the
relationship directly: *"This looks like the NDBM interface for dbm use."* — **looks
like**, not **derived from**. It is a reimplementation on top of gdbm, so there is no
older permissive original to fall back to.

---

## 4. Non-FSF copyright holders — four, all build tooling

| Holder | File | Its own terms |
|---|---|---|
| X Consortium | `build-aux/install-sh:10` | MIT, plus "FSF changes to this file are in the public domain" |
| Ulrich Drepper | `po/Makefile.in.in:2` | permissive — "permitted in any medium without royalty" |
| Bootstrap Authors | `build-aux/ltmain.sh:75`, `:1539` | dual MIT / GPL-2-or-later — the only true dual licence in the tree |
| Sergey Poznyakoff | `doc/gendocs.pl:2` | GPL-3-or-later; header still reads "This file is part of GNU Pies" |

Translators hold no copyright: `po/Makevars:38` sets
`COPYRIGHT_HOLDER = Free Software Foundation, Inc.` and every `.po` reads *"distributed
under the same license as the gdbm package."*

---

## 5. Finding: one genuine relicensed import, `src/gettext.h`

Lines 5-12 contradict themselves:

```
   under the terms of the GNU General Public License as published
   by the Free Software Foundation; either version 3, or (at your option)
   any later version.
   ...
   Library General Public License for more details.
```

The grant says GPL-3+. The warranty paragraph still says **Library** GPL. Upstream
gettext ships this same convenience header — same `_LIBGETTEXT_H` guard, same macro
body — under **LGPL-2.1-or-later** (compare this host's `/usr/share/gettext/gettext.h`,
owned by `gettext 0.23.1-2`). gdbm took an LGPL file, relicensed it to GPL-3+, and
missed a line.

**It does not help.** `src/Makefile.am:58-63` lists it under `noinst_HEADERS` — not
installed, not part of the ABI — and it is an i18n macro wrapper, not database code. The
LGPL original is available straight from gettext; nobody needs to take it from gdbm.

---

## 6. Every permissive thing in the tree, and why none of it is usable

| Material | Terms | Why it is useless here |
|---|---|---|
| `m4/*.m4` (22 files), `aclocal.m4`, `configure`, `config.rpath`, `po/Rules-quot` | "unlimited permission to copy and/or distribute" | autotools macros, consumed at configure time, never shipped |
| `build-aux/install-sh` | MIT (X Consortium) + public-domain modifications | an install script |
| `build-aux/ltmain.sh` | dual MIT / GPL-2+ | libtool driver, build-time |
| `config.guess`, `config.sub`, `texinfo.tex` | GPL-3+ with the Autoconf §7 additional permission | build-time only |
| `tools/gram.c`, `tools/gram.h` | Bison skeleton exception — *"distribute that work under terms of your choice"* | covers the **skeleton** only, not the grammar actions in `gram.y` (GPL-3+); and it is the `gdbmtool` CLI parser, not the library |
| `doc/` | GFDL-1.3-or-later | documentation, and a different licence, still not usable |

Searches returning **zero** hits across the tree: `linking exception`,
`alternative licen`, `commercial licen`, `Apache`. No bundled gnulib, no vendored
`snprintf.c` / `regex*` / `strtol*`. `ChangeLog:4740` records the only bundled
dependency gdbm ever had being **deleted** in 2007 (`* getopt.h, getopt.c: Remove.`).

### Corrected file census

| Class | Count |
|---|---|
| GPL-3-or-later | 96 |
| GPL-or-later, version stated below line 40 | 73 |
| no licence header at all (`.gmo`, stamp files, `README`, `AUTHORS`, `THANKS`) | 41 |
| copyright but no grant in the header (`.po`, `NEWS`, `INSTALL`) | 21 |
| unlimited permission (permissive) | 22 |
| **LGPL** | **0** |
| MIT + public domain | 1 |
| GFDL-1.3-or-later | 3 |
| GPL-3-only | 1 (`COPYING`, the licence text itself) |

An earlier pass of this audit bucketed five `m4/` files as LGPL. That was wrong — they
grant unlimited permission and merely *mention* LGPL while describing what the gettext
*library* is under. Corrected above: no file in this tree is LGPL.

Files in `src/`, `compat/`, `tools/` with no copyright at all: **zero**.

---

## 7. Judgement

No part of gdbm 1.26 can go into a proprietary product without triggering GPL
obligations. Both shipped libraries are strong copyleft top to bottom, and the
compatibility layer is no different from the core.

The estate's position is unchanged and correct: **gdbm is dropped**, via
`work/recipes/recipes-devtools/python/python3_%.bbappend` (`PACKAGECONFIG:remove = "gdbm"`).
Nothing imports `dbm`; sqlite3 already ships under `blessing`.

### Recorded, not acted on

1. **The OE-core recipe token is factually wrong.** `GPL-3.0-only` matches no file in the
   tree. This matters for licence-compatibility answers elsewhere in the estate and for
   anyone auditing the manifest. It does not weaken the copyleft.
2. **`meta-gplv2` carries `gdbm_1.8.3.bb` with `LICENSE = "GPL-2.0-or-later"`.** That is
   the genuine pre-2007 gdbm. Named because it exists, not because it solves anything —
   it is still copyleft. **Also: that layer checkout is dated 2026-08-21, which is
   August-era and therefore out of scope under the fresh-start rule.**
3. **The same `LIC_FILES_CHKSUM`-reads-only-COPYING mechanism will have mis-declared
   other recipes in the estate.** Naming the adjacent work and stopping.

---

## Verification

Claims independently re-checked against disk after the census, not taken on report:

- recipe token and `LIC_FILES_CHKSUM` — read from `gdbm_1.26.bb` lines 7-8
- the 75 / 99 grant split — `grep -rl`, wrap-tolerant pattern
- the three installed headers and their `_HEADERS` install targets — `Makefile.am`
- `ChangeLog:4733` relicensing entry — read in context
- zero Regents / AT&T / Paxson hits — `grep -rl` over the whole tree
- all `compat/` copyright holders — enumerated, all FSF
- `src/gettext.h` grant-vs-warranty contradiction — read directly
- `meta-gplv2/recipes-support/gdbm/gdbm_1.8.3.bb` exists, `LICENSE = "GPL-2.0-or-later"`

`/home/google/Downloads/gdbm-1.26` was not modified, moved, built, or configured.
