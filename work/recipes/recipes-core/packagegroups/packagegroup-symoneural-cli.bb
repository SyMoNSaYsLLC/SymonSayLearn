# The deployable CLI runtime surface: the two direct upstream Python packages
# (the Messages-dialect client SDK and the MCP SDK) and, through their RDEPENDS, the runtime closure their
# wheels declare (tools/check-python-runtime-closures.py --runtime CLI must PASS for
# this group to mean anything). The API packagegroup supplies the shared web stack.
SUMMARY = "SyMoNeuRaL CLI runtime - Messages-dialect client SDK + MCP Python closure"
LICENSE = "MIT"
inherit packagegroup

RDEPENDS:${PN} = " \
    symoneural-anthropic-sdk-python \
    symoneural-mcp-python-sdk \
    packagegroup-symoneural-api \
"
