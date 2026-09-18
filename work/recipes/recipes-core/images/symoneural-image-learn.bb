# Clean-target proof image for the SymonSayLearn runtime.
#
# Every other image in this directory proves ONE runtime imports and runs from a
# feed-assembled root. This one proves the COMPOSITION: that the gateway, the chat
# unit's Python surface and the bring-up glue install together, from packages, with
# no source tree, no devtool workspace, no pip and no build frontend present.
#
# It is also the artifact a release is cut from. `symoneural-image-learn` at tag
# vX.Y.Z is what "the SymonSayLearn runtime, version X.Y.Z" means.
SUMMARY = "SyMoNeuRaL SymonSayLearn clean-root proof image"
LICENSE = "MIT"

inherit image

# The recommended slices are named explicitly because NO_RECOMMENDATIONS is set
# below. A proof image's manifest is its install record, and a package that arrives
# through a recommendation rather than a declaration makes that record a guess.
#
# symoneural-learn-web is NOT here, and its absence is a recorded barrier rather than
# an oversight. The web interface is Next.js on Node, and neither is acquired into
# this estate: upstream/web/ holds workerd and workers-sdk, and there is no Node
# recipe. Listing a package that cannot build would make this image unbuildable and
# hide a missing acquisition behind a build error. See
# work/recipes/recipes-learn/symoneural-learn-web/ for the recipe that is waiting on
# it, and rules section 3.8 for why a barrier is raised rather than worked around.
IMAGE_INSTALL = " \
    packagegroup-symoneural-learn \
"
IMAGE_FEATURES = ""
IMAGE_LINGUAS = ""
IMAGE_FSTYPES = "tar.gz"

# no kernel, no bootloader: this is a userspace root for import and service proofs
IMAGE_INSTALL:remove = "packagegroup-core-boot"
NO_RECOMMENDATIONS = "1"

# qemux86-64's machine conf adds qemuboot, which drags qemu-system-native,
# qemu-helper-native and (through virglrenderer) mesa-tools-native into a build whose
# only product is a rootfs tarball. Nothing boots this tarball under qemu;
# tools/*-clean-root-proof runs the target interpreter through its own ld.so.
IMAGE_CLASSES:remove = "qemuboot"

# image.bbclass hooks do_build on virtual/kernel:do_deploy and do_rootfs on
# virtual/kernel:do_packagedata for depmod data. A userspace proof root installs no
# kernel modules; both hooks are emptied.
KERNEL_DEPLOY_DEPEND = ""
KERNELDEPMODDEPEND = ""

# ---------------------------------------------------------------------------
# LICENCE POLICY, ENFORCED BY THE BUILD
#
# work/tools/licence-audit.py found GPL-3.0-only gdbm in the api and common proof
# images. gdbm arrives through python3's dbm module, so nothing named it directly
# and nothing would have caught it by reading a recipe. A hand-maintained
# exclusion list would miss the next one the same way.
#
# INCOMPATIBLE_LICENSE makes BitBake refuse to place a matching package in the
# rootfs at all. The build fails instead of shipping, which is the only kind of
# guard worth having: it cannot pass while being wrong.
#
# AGPL is listed even though none is present today. It is the category that would
# be triggered by SERVING the product over a network rather than by distributing
# it, which is exactly what this runtime does, so it is the most expensive one to
# discover late.
#
# LGPL is deliberately NOT here. glibc is LGPL-2.1 and is the C library; excluding
# it would leave nothing to run. LGPL permits proprietary use when the library is
# dynamically linked and the user can relink, which is how this image links it.
INCOMPATIBLE_LICENSE = "GPL-3.0* LGPL-3.0* AGPL-3.0* SSPL*"

# gdbm is dropped in recipes-devtools/python/python3_%.bbappend, NOT here. An image
# recipe's variables apply to the image, not to other recipes, so setting
# PACKAGECONFIG from this file would parse cleanly and do nothing at all.
