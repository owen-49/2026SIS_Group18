const DEMO_PAPERS = [
  { citationKey: "vaswani2017attention", title: "Attention Is All You Need", authors: "Vaswani et al.", venue: "NeurIPS", year: "2017", url: "https://arxiv.org/abs/1706.03762", status: "linked" },
  { citationKey: "devlin2019bert", title: "BERT: Pre-training of Deep Bidirectional Transformers", authors: "Devlin et al.", venue: "NAACL", year: "2019", url: "https://aclanthology.org/N19-1423", status: "linked" },
  { citationKey: "brown2020language", title: "Language Models are Few-Shot Learners", authors: "Brown et al.", venue: "NeurIPS", year: "2020", url: "https://arxiv.org/abs/2005.14165", status: "linked" },
  { citationKey: "lewis2020retrieval", title: "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks", authors: "Lewis et al.", venue: "NeurIPS", year: "2020", url: "https://arxiv.org/abs/2005.11401", status: "linked" },
];

chrome.runtime.onInstalled.addListener(async () => {
  await chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
  const stored = await chrome.storage.local.get("claimtracePapers");
  if (!stored.claimtracePapers) {
    await chrome.storage.local.set({ claimtracePapers: DEMO_PAPERS, claimtraceSource: "demo" });
  }
});

chrome.runtime.onMessage.addListener((message, sender) => {
  if (message.type === "bibliography_detected" && Array.isArray(message.papers) && message.papers.length) {
    void chrome.storage.local.set({
      claimtracePapers: message.papers,
      claimtraceSource: "overleaf",
      claimtraceUpdatedAt: Date.now(),
    });
  }

  if (message.type === "open_side_panel" && sender.tab?.id) {
    void chrome.sidePanel.open({ tabId: sender.tab.id });
  }
});
