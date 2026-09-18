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
