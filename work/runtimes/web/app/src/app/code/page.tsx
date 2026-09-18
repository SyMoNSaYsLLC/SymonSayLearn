// SPDX-License-Identifier: FSL-1.1-ALv2
// Copyright 2026 SymonSaysLLC
// SyMoNsAyLeaRn — SyMoNeuRaL, a subdivision of SymonSaysLLC. Terms: see LICENSE.
/* The Code surface. Three surfaces differ in which tier they prefer and in what they
 * say; the conversation itself is one component, so a fix to streaming or to reasoning
 * handling lands on all three at once instead of in whichever copy someone remembered. */
import ConversationSurface from "@/components/ConversationSurface";

export default function Page() {
  return (
    <ConversationSurface
      tier="opus"
      title="Code"
      subtitle="Writing and running code against this estate."
      placeholder="Describe the change"
    />
  );
}
