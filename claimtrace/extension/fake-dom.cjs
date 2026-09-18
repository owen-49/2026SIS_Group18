"use strict";

// A hand-built DOM for running src/content.js inside node:vm.
//
// content.js is a classic script injected into someone else's page, so testing
// it means giving it a page. This is the smallest one that carries the hover
// path end to end: elements with id and class selectors, text nodes, ranges with
// rectangles, timers and animation frames the test steps by hand, a chrome stub
// that records what the content script reports, and a performance stub so the
// hover measurement is actually taken.
//
// It is not a browser, and a test written against it proves what the card is
// told to display, not what a user sees. There is no layout (each line's
// rectangle is whatever the test hands it), no CSS, no paint, no HTML entity
// decoding, and no real clock, so no duration measured here is a latency
// measurement. innerHTML is write-only: the parser fills the tree, and tests
// read it back through textContent and selectors.

const ATTRIBUTES = /([^\s"'>/=]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+)))?/g;
const TAGS = /<(\/?)([a-zA-Z][\w-]*)((?:\s+[^\s"'>/=]+(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s"'>]+))?)*)\s*(\/?)>/g;
const RECT = { top: 0, left: 0, right: 320, bottom: 180, width: 320, height: 180 };

function createElement(document, name) {
  const element = {
    nodeType: 1,
    ownerDocument: document,
    tagName: String(name).toUpperCase(),
    childNodes: [],
    parentNode: null,
    attributes: {},
    dataset: {},
    style: {},
    id: "",
    hidden: false,
    rect: { ...RECT },
    rects: null,
    scrolls: 0,
  };
  let classes = [];

  Object.defineProperties(element, {
    className: {
      get: () => classes.join(" "),
      set: (value) => { classes = String(value).split(/\s+/).filter(Boolean); },
    },
    classList: {
      get: () => ({
        add: (...names) => names.forEach((n) => { if (!classes.includes(n)) classes.push(n); }),
        remove: (...names) => { classes = classes.filter((c) => !names.includes(c)); },
        contains: (name) => classes.includes(name),
      }),
    },
    children: { get: () => element.childNodes.filter((node) => node.nodeType === 1) },
    textContent: {
      get: () => element.childNodes.map(textOf).join(""),
      set: (value) => {
        element.childNodes = [];
        if (value !== undefined && value !== null && value !== "") {
          element.childNodes.push(textNode(element, value));
        }
      },
    },
    innerHTML: {
      set: (value) => {
        element.childNodes = [];
        parseInto(document, element, String(value));
      },
    },
  });

  element.setAttribute = (key, value) => {
    element.attributes[key] = String(value);
    if (key === "class") element.className = value;
    else if (key === "id") element.id = value;
    // A boolean attribute: the card's passage section ships hidden in its markup.
    else if (key === "hidden") element.hidden = true;
  };
  element.appendChild = (child) => { appendChild(element, child); return child; };
  element.remove = () => {
    const siblings = element.parentNode?.childNodes;
    if (!siblings) return;
    const index = siblings.indexOf(element);
    if (index >= 0) siblings.splice(index, 1);
    element.parentNode = null;
  };
  element.matches = (selector) => matches(element, selector);
  element.closest = (selector) => {
    for (let node = element; node?.nodeType === 1; node = node.parentNode) {
      if (matches(node, selector)) return node;
    }
    return null;
  };
  element.querySelector = (selector) => element.querySelectorAll(selector)[0] || null;
  element.querySelectorAll = (selector) =>
    descendants(element).filter((node) => matches(node, selector));
  element.getBoundingClientRect = () => element.rect;
  element.scrollIntoView = () => { element.scrolls += 1; };
  element.addEventListener = (type, handler) => {
    (element.listeners ||= {})[type] = handler;
  };

  return element;
}

function textNode(parent, data) {
  return { nodeType: 3, data: String(data), parentNode: parent };
}

function textOf(node) {
  return node.nodeType === 3 ? node.data : node.childNodes.map(textOf).join("");
}

function appendChild(parent, child) {
  child.parentNode = parent;
  parent.childNodes.push(child);
}

function descendants(root) {
  const found = [];
  const walk = (node) => node.childNodes.forEach((child) => {
    if (child.nodeType !== 1) return;
    found.push(child);
    walk(child);
  });
  walk(root);
  return found;
}

// Compound selectors only -- #id, .class, tag, and combinations of those. No
// descendant combinators, no pseudo-classes: content.js asks for neither, and a
// selector engine that quietly accepted one it mishandled would be worse than
// one that returns nothing.
function matches(element, selector) {
  return String(selector).split(",").some((part) => {
    const compound = part.trim();
    if (!compound) return false;
    const id = compound.match(/#([^.#\s]+)/);
    if (id && element.id !== id[1]) return false;
    const tag = compound.match(/^([a-zA-Z][\w-]*)/);
    if (tag && element.tagName.toLowerCase() !== tag[1].toLowerCase()) return false;
    return [...compound.matchAll(/\.([^.#\s]+)/g)].every(([, name]) => element.classList.contains(name));
  });
}

function parseInto(document, parent, html) {
  const stack = [parent];
  let cursor = 0;
  TAGS.lastIndex = 0;
  let tag;
  while ((tag = TAGS.exec(html))) {
    const [, closing, name, attributeText, selfClosing] = tag;
    if (tag.index > cursor) appendChild(stack.at(-1), textNode(stack.at(-1), html.slice(cursor, tag.index)));
    cursor = TAGS.lastIndex;
    if (closing) {
      const open = stack.findLastIndex((node) => node.tagName?.toLowerCase() === name.toLowerCase());
      if (open > 0) stack.length = open;
      continue;
    }
    const element = createElement(document, name);
    ATTRIBUTES.lastIndex = 0;
    let attribute;
    while ((attribute = ATTRIBUTES.exec(attributeText))) {
      const value = attribute[2] ?? attribute[3] ?? attribute[4] ?? "";
      element.setAttribute(attribute[1], value);
    }
    appendChild(stack.at(-1), element);
    if (!selfClosing) stack.push(element);
  }
  if (cursor < html.length) {
    appendChild(stack.at(-1), textNode(stack.at(-1), html.slice(cursor)));
  }
}

function createRange(document) {
  const range = {
    startNode: null,
    setStart(node) { range.startNode = node; },
    setEnd() {},
  };
  range.getClientRects = () => range.startNode?.parentNode?.rects || [];
  range.getBoundingClientRect = () => range.getClientRects()[0] || { ...RECT };
  return range;
}

// content.js is a classic script; a directory of tests that share a page is not
// a thing it supports, so each test builds its own sandbox and its own copy of
// the script runs in it.
function createDom(options = {}) {
  const logs = [];
  const messages = [];
  const fetches = [];
  const measures = [];
  const highlights = new Map();
  const marks = [];
  const storage = { ...(options.storage || {}) };
  const listeners = {};
  const timers = new Map();
  const frames = new Map();
  let timerId = 0;
  let frameId = 0;
  let markAt = 0;

  const document = {
    nodeType: 9,
    childNodes: [],
    createElement: (name) => createElement(document, name),
    createTextNode: (data) => textNode(null, data),
    createRange: () => createRange(document),
    createTreeWalker: (root) => {
      const nodes = [];
      const walk = (node) => (node.childNodes || []).forEach((child) => {
        if (child.nodeType === 3) nodes.push(child);
        walk(child);
      });
      walk(root);
      let index = 0;
      return { nextNode: () => nodes[index++] || null };
    },
    addEventListener: (type, handler) => { (listeners[type] ||= []).push(handler); },
    querySelector: (selector) => document.querySelectorAll(selector)[0] || null,
    querySelectorAll: (selector) => descendants(document).filter((node) => matches(node, selector)),
    getElementById: (id) => descendants(document).find((node) => node.id === id) || null,
  };

  const html = document.createElement("html");
  const body = document.createElement("body");
  document.documentElement = html;
  document.body = body;
  appendChild(document, html);
  appendChild(html, body);

  const content = document.createElement("div");
  content.className = "cm-content";
  appendChild(body, content);
  (options.lines || []).forEach((text, index) => {
    const line = document.createElement("div");
    line.className = "cm-line";
    line.textContent = text;
    line.rects = (options.rects || {})[index] || [{ left: 40, top: 100, right: 260, bottom: 118, width: 220, height: 18 }];
    line.rect = line.rects[0];
    appendChild(content, line);
  });

  const boundary = (type) => (event) => (listeners[type] || []).forEach((handler) => handler(event));

  const sandbox = {
    document,
    window: {
      innerHeight: 900,
      innerWidth: 1200,
      // Ids are never reused: a cleared timer that a later one had taken the id
      // of would cancel work the test never asked it to cancel.
      setTimeout: (handler, delay) => { timerId += 1; timers.set(timerId, { handler, delay }); return timerId; },
      clearTimeout: (id) => timers.delete(id),
      requestAnimationFrame: (handler) => { frameId += 1; frames.set(frameId, handler); return frameId; },
    },
    Node: { ELEMENT_NODE: 1 },
    NodeFilter: { SHOW_TEXT: 4 },
    MutationObserver: class { observe() {} disconnect() {} },
    console: {
      log: (...args) => logs.push(args.join(" ")),
      warn: (...args) => logs.push(args.join(" ")),
      info: (...args) => logs.push(args.join(" ")),
      error: (...args) => logs.push(args.join(" ")),
    },
    chrome: {
      runtime: {
        onMessage: { addListener: (handler) => { sandbox.messageHandler = handler; } },
        sendMessage: (message) => messages.push(message),
      },
      storage: {
        local: {
          get: (keys, callback) => callback(Object.fromEntries(
            (Array.isArray(keys) ? keys : [keys]).filter((key) => key in storage).map((key) => [key, storage[key]]),
          )),
          set: (values) => Object.assign(storage, values),
        },
        onChanged: { addListener: (handler) => { sandbox.storageHandler = handler; } },
      },
    },
    fetch: (url, init) => { fetches.push({ url, init }); throw new Error("the content script must not fetch"); },
  };

  if (options.css !== false) {
    sandbox.Highlight = class { constructor(...ranges) { this.ranges = ranges; } };
    sandbox.CSS = { highlights };
  }
  if (options.performance !== false) {
    // Both spellings, as in a page: content.js reaches for window.performance.
    sandbox.performance = sandbox.window.performance = {
      // The sandbox has no clock to measure against, so it advances one instead:
      // strict.js proves the hover path takes a measurement and reports it, not
      // that the card appeared in 12.5 ms.
      mark: (name) => { marks.push(name); markAt = measures.length * 12.5; },
      measure: (name, startMark) => {
        if (!marks.includes(startMark)) throw new Error(`measure(${name}) without mark(${startMark})`);

        const entry = { name, duration: markAt + 12.5 };
        measures.push(entry);
        return entry;
      },
    };
  }

  sandbox.logs = logs;
  sandbox.messages = messages;
  sandbox.fetches = fetches;
  sandbox.measures = measures;
  sandbox.marks = marks;
  sandbox.highlights = highlights;
  sandbox.storage = storage;
  sandbox.setFindings = (findings) => {
    storage.claimtraceFindings = findings;
    sandbox.storageHandler?.({ claimtraceFindings: { newValue: findings } }, "local");
  };
  sandbox.reports = (type) => messages.filter((message) => message.type === type);
  sandbox.hoverCard = () => document.getElementById("claimtrace-citation-hover");
  sandbox.textIn = (selector) => sandbox.hoverCard()?.querySelector(selector)?.textContent;
  sandbox.elementIn = (selector) => sandbox.hoverCard()?.querySelector(selector);
  // Timers and frames queued by the callbacks that run here are left for the
  // next flush, so a test that hides the card does not also dismiss the prompt.
  sandbox.flushFrames = () => {
    const due = [...frames.values()];
    frames.clear();
    due.forEach((handler) => handler());
  };
  sandbox.flushTimers = () => {
    const due = [...timers.values()];
    timers.clear();
    due.forEach((timer) => timer.handler());
  };
  sandbox.move = (x, y) => { boundary("mousemove")({ clientX: x, clientY: y }); sandbox.flushFrames(); };
  sandbox.leave = () => { boundary("mouseleave")({}); sandbox.flushTimers(); };
  sandbox.focusCitation = (locationId) => {
    const responses = [];
    sandbox.messageHandler?.({ type: "focus_citation", locationId }, {}, (response) => responses.push(response));
    sandbox.flushFrames();
    sandbox.flushTimers();
    return responses;
  };

  return sandbox;
}

module.exports = { createDom };
