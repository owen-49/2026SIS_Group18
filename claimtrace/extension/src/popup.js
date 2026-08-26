const readPageBtn = document.getElementById("readPageBtn");
const readStatus = document.getElementById("readStatus");
const pageTitle = document.getElementById("pageTitle");
const pageContent = document.getElementById("pageContent");

readPageBtn.addEventListener("click", async () => {

  readStatus.textContent = "Reading page...";

  const [tab] = await chrome.tabs.query({
    active: true,
    currentWindow: true
  });

  chrome.tabs.sendMessage(
    tab.id,
    { action: "getPageContent" },
    (response) => {

      if (chrome.runtime.lastError) {

        console.error(
          chrome.runtime.lastError.message
        );

        readStatus.textContent =
          "Could not read this page.";

        return;
      }

      if (!response) {

        readStatus.textContent =
          "No page content received.";

        return;
      }

      if (response.editorFound) {

        readStatus.textContent =
          "Overleaf editor detected ✓";

      } else {

        readStatus.textContent =
          "Page received, but editor not detected";

      }

      pageTitle.textContent =
        response.title;

      pageContent.textContent =
        response.content;
    }
  );
});