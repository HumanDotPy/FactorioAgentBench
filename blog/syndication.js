const container = document.querySelector("[data-feed][data-project]");

if (container) {
  const feedUrl = container.dataset.feed;
  const project = container.dataset.project;

  fetch(feedUrl)
    .then((response) => {
      if (!response.ok) throw new Error(`Feed returned ${response.status}`);
      return response.json();
    })
    .then((feed) => {
      const items = Array.isArray(feed.items)
        ? feed.items.filter((item) => Array.isArray(item.projects) && item.projects.includes(project))
        : [];

      if (items.length === 0) return;

      const fragment = document.createDocumentFragment();
      for (const item of items) {
        const article = document.createElement("article");
        article.className = "post-row featured-post";

        const meta = document.createElement("div");
        meta.className = "post-meta";
        const source = document.createElement("span");
        source.textContent = "From HumanDotPy";
        const time = document.createElement("time");
        const date = new Date(item.date);
        time.dateTime = date.toISOString();
        time.textContent = date.toLocaleDateString("en-US", {
          month: "long",
          day: "numeric",
          year: "numeric",
          timeZone: "UTC",
        });
        meta.append(source, time);

        const content = document.createElement("div");
        const status = document.createElement("p");
        status.className = "post-status";
        status.textContent = item.kind || "General essay";
        const heading = document.createElement("h2");
        const titleLink = document.createElement("a");
        titleLink.href = item.url;
        titleLink.textContent = item.title;
        heading.append(titleLink);
        const description = document.createElement("p");
        description.textContent = item.description || "";
        const readLink = document.createElement("a");
        readLink.className = "text-link";
        readLink.href = item.url;
        readLink.textContent = "Read at HumanDotPy";
        content.append(status, heading, description, readLink);

        article.append(meta, content);
        fragment.append(article);
      }

      container.replaceChildren(fragment);
    })
    .catch(() => {
      // Keep the server-rendered fallback when the remote feed is unavailable.
    });
}
