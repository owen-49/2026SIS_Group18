# Storyboard demonstration with the published BERT paper

The local `/verify/example` and `/audit/example` routes follow the supplied
storyboard and share the published BERT paper. They use local fixtures and never
run an LLM, a publication lookup, or PDF parsing. The interface uses normal product
labels at the user's request; this document records the fixture boundary.

1. Open `/verify/example`. Rich opens at original Figure 1. Scroll upward to read
   from the beginning; all 16 pages, 5 figures, 8 tables, references and appendices
   remain available. The original PDF is bundled for exact typesetting.
2. Click **Find citation**, highlight **BERT’s model architecture**, including
   **Vaswani et al. (2017)**, then click **Analyze selection**. The Partial result
   uses an actual short excerpt from Attention Is All You Need, PDF page 2.
3. Author–year citations throughout the paper are clickable. Clicking selects
   the sentence and reference; dragging over a cited sentence also works. Shared
   citations with multiple years require choosing a source. Changing a selection
   clears the previous result and manual source override.
4. Try the SQuAD dataset sentence in section 4.2 or the ELMo feature-based sentence
   in the introduction for Support results. ELMo, ULMFiT, SQuAD, GLUE and GloVe use
   actual published abstract excerpts. Comparisons that exceed an abstract's scope
   return Partial. Identified references without source text remain Not judged
   and ask for the source PDF; no evidence is invented for these cases.
5. Switch to **Batch audit** in the sidebar and click **Run audit**. The complete
   bibliography contains 56 entries. Three input years are deliberately altered
   (Vaswani, Howard/Ruder, Zellers); the original published reference list is
   correct. Other fixture states include verified records, ambiguous matches,
   one record not found, and lookup timeouts. Search and status filters work.
6. Return to Verify for the evidence shot. The Overleaf extension is unchanged;
   record its actual bibliography Audit flow separately.

Results, confidence, similarity, lookup states and timestamps are local scripted
fixtures. They are not current database responses or measured model accuracy.
No changes are uploaded unless the user explicitly asks.

Sources and licensing: `../src/assets/demo/README.md`. Full-paper conversion and
bibliography generation: `../scripts/prepare-bert-demo.py`.
