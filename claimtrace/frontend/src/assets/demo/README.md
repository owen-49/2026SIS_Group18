# Published-paper assets for the storyboard example

Paper: Jacob Devlin, Ming-Wei Chang, Kenton Lee, and Kristina Toutanova (2019).
BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding.
NAACL-HLT 2019, pp. 4171–4186. DOI: 10.18653/v1/N19-1423.

- Record: https://aclanthology.org/N19-1423/
- Original PDF: https://aclanthology.org/N19-1423.pdf
- License: CC BY 4.0, per https://aclanthology.org/faq/copyright/
- Copyright: 2019 Association for Computational Linguistics.

`bert-pretraining-finetuning.png`: original Figure 1, PDF page 3 (printed p. 4173).
`bert-input-representation.png`: original Figure 2, PDF page 5 (printed p. 4175).

All five figures and eight tables are cropped from the official PDF at 3 pixels
per PDF point. Exact crop coordinates are recorded in the generator. Captions
remain alongside the images; figure content is unchanged. The complete text is
reflowed with the first fragment's page location retained when a paragraph crosses
a column or page boundary. Original superscript footnotes and author–year citation
notation are preserved. Use the bundled original PDF for exact typography.

The Verify architecture fixture is PARTIAL, not a live model result. Its excerpt
is from Attention Is All You Need (Vaswani et al., 2017), PDF page 2, section 3.1:
https://papers.nips.cc/paper_files/paper/2017/file/3f5ee243547dee91fbd053c1c4a845aa-Paper.pdf

Additional original source abstracts are stored in `src/data/demoSourceProfiles.ts`:

- Peters et al. (2018), ELMo: https://aclanthology.org/N18-1202/ — CC BY 4.0
- Howard and Ruder (2018), ULMFiT: https://aclanthology.org/P18-1031/ — CC BY 4.0
- Rajpurkar et al. (2016), SQuAD: https://aclanthology.org/D16-1264/ — CC BY 4.0
- Wang et al. (2018), GLUE: https://aclanthology.org/W18-5446/ — CC BY 4.0
- Pennington et al. (2014), GloVe: https://aclanthology.org/D14-1162/ — CC BY-NC-SA 3.0

These excerpts are attributed in each result by title, authors and publication
link. This local educational demonstration retains source provenance and license
metadata in `demoSourceProfiles.ts`.

The Audit fixture uses all 56 references extracted from BERT's bibliography.
Three input years are deliberately changed to demonstrate field differences;
other scripted outcomes exercise review, not-found and timeout states. BERT's
original reference list is correct. No result should be described as a fresh
publication lookup or an actual error found in the original paper.

## Full-document generation

Run the repository converter with Java 11 in local mode (`hybrid="off"`,
`format="json"`), then:

```sh
python claimtrace/frontend/scripts/prepare-bert-demo.py --pdf bert.pdf --layout bert.json
```

This regenerates all 16 page text fixtures, Rich Markdown, figures, tables and
original PDF. Crop coordinates are recorded in the generator. Full text is
reflowed, so the bundled original PDF remains authoritative for typography.
Original PDF SHA-256:
`987545ffb087f1ece898142c403a516baeabeb70ce19089397fac6f7db12c3d4`.
