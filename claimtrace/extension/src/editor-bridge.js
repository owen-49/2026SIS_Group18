// Runs in Overleaf's page world. Read the editor document without changing it.
// CodeMirror virtualizes its DOM, so rendered lines are not a complete file.
(() => {
  function editorDocument() {
    for (const element of document.querySelectorAll('.cm-content')) {
      const view = element.cmView?.rootView?.view || element.cmView?.view;
      if (view?.state?.doc) return {
        text: view.state.doc.toString(),
        lineOffsets: Array.from(document.querySelectorAll('.cm-line'), line => {
          try { return view.posAtDOM(line); } catch { return null; }
        }),
      };
    }
    for (const element of document.querySelectorAll('.ace_editor')) {
      if (element.env?.editor?.getValue) return { text: element.env.editor.getValue(), lineOffsets: [] };
    }
    return null;
  }
  document.addEventListener('claimtrace:read-editor', () => {
    let snapshot = { text: null, lineOffsets: [] };
    try { snapshot = editorDocument() || snapshot; } catch { /* Fail closed instead of uploading a viewport fragment. */ }
    document.dispatchEvent(new CustomEvent('claimtrace:editor-document', {
      detail: JSON.stringify(snapshot),
    }));
  });
})();
