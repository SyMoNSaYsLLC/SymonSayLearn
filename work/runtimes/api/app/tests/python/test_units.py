# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright 2026 SymonSaysLLC
# SyMoNsAyLeaRn — SyMoNeuRaL, a subdivision of SymonSaysLLC. Terms: see LICENSE.
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from symoneural_api import units


class UnitsTest(unittest.TestCase):
    # These assert INVARIANTS, not a census. The previous version froze the list at
    # eight names and range(8801, 8809); adding the image and sigils units on
    # 2026-09-17 broke all three assertions, and the breakage was not caught because
    # this suite is not the one tools/test-estate-operators.py runs. A test that has
    # to be edited every time the product grows is a changelog, not a test.
    def test_ports_are_one_block_unique_and_contiguous(self):
        ports = [u.port for u in units.REGISTRY.values()]
        self.assertEqual(len(set(ports)), len(ports), "two units share a port: %r" % (ports,))
        self.assertEqual(ports, sorted(ports), "REGISTRY order must follow port order")
        self.assertEqual(ports, list(range(8801, 8801 + len(ports))),
                         "ports must be a contiguous block from 8801: %r" % (ports,))
        self.assertNotIn(8800, ports, "8800 is the read-only demo (R14); no unit may claim it")

    def test_every_unit_is_complete(self):
        for name, u in units.REGISTRY.items():
            self.assertEqual(u.name, name)
            self.assertIn(u.resource, set(units.Resource), name)
            self.assertEqual(u.token_env, "SYM_%s_TOKEN" % name.upper(), name)
            self.assertTrue(u.description.strip(), "%s has no description" % name)

    def test_gpu_units_are_exactly_the_gpu_resource(self):
        self.assertEqual([u.name for u in units.gpu_units()],
                         [u.name for u in units.REGISTRY.values()
                          if u.resource is units.Resource.GPU])
        self.assertIs(units.unit("ravencalc").resource, units.Resource.CPU)
        self.assertIs(units.unit("streamer").resource, units.Resource.NET)

    def test_no_port_literal_outside_this_registry(self):
        """units.py is THE definition. A second copy elsewhere silently drifts.

        Known duplicates, recorded rather than asserted away, because fixing them
        changes two other runtimes' behaviour: symoneural_llm/main.py DEFAULT_PORT
        = 8802 and symoneural_ravencalc/service.py SYM_RAVENCALC_PORT default 8801.
        A worker should be TOLD its port by the supervisor's argv, not compile one in.
        """
        import re
        src = Path(units.__file__).read_text()
        literals = {int(m) for m in re.findall(r"port=(\d{4})", src)}
        self.assertEqual(literals, {u.port for u in units.REGISTRY.values()})

    def test_env_names(self):
        u = units.unit("chat")
        self.assertEqual(u.token_env, "SYM_CHAT_TOKEN")
        self.assertEqual(u.enabled_variable, "SYM_CHAT_ENABLED")

    def test_backing_packages_all_estate(self):
        for name, pkgs in units.backing_packages().items():
            self.assertTrue(pkgs, name)
            for p in pkgs:
                self.assertTrue(p.startswith("symoneural-"), p)

    def test_unknown_unit(self):
        with self.assertRaises(KeyError):
            units.unit("nosuch")


if __name__ == "__main__":
    unittest.main()
