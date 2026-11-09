/* A stand-in for window.pywebview.api so the real app.js can be driven in a plain browser
   for visual testing. Mirrors the shapes returned by brightspace_downloader/api.py. */
"use strict";

const COURSES = [
  { id: 844457, name: "Software Engineering Methods (SEM)", code: "CSE2115+2026+1", pinned: true, active: true },
  { id: 774607, name: "Introduction to Programming", code: "CSE1100+2025+1", pinned: false, active: true },
  { id: 774613, name: "Reasoning and Logic", code: "CSE1300+2025+1", pinned: false, active: true },
  { id: 202, name: "Archived Databases Course", code: "OLD-DB", pinned: false, active: false },
];

const TREE = {
  fileCount: 7,
  skipped: { link: 2, media: 1 },
  skippedText: "2 web links, 1 embedded video",
  defaultDir: "C:\\Users\\you\\Documents\\Brightspace",
  nodes: [
    { type: "folder", id: "m1", name: "Software Engineering Methods (SEM)", children: [
      { type: "folder", id: "m2", name: "Week 1", children: [
        { type: "file", id: 1, name: "Reading Material - Copy.html", title: "Reading Material", path: "x" },
        { type: "file", id: 2, name: "Lecture 1 - Introduction.pdf", title: "Lecture 1.1 - Introduction and Course Organisation", path: "x" },
        { type: "file", id: 3, name: "Slides - Agility.pdf", title: "Lecture 1.2 - Practicing Agility in SE", path: "x" },
        { type: "folder", id: "m3", name: "Assignment 1 - Requirements", children: [
          { type: "file", id: 4, name: "SEM_Assignment_1.pdf", title: "Assignment 1", path: "x" },
        ]},
      ]},
      { type: "folder", id: "m4", name: "Week 2", children: [
        { type: "file", id: 5, name: "Lecture 2.pdf", title: "Lecture 2.1", path: "x" },
        { type: "file", id: 6, name: "notes.pdf", title: "Notes copy A", path: "x" },
        { type: "file", id: 7, name: "notes (2).pdf", title: "Notes copy B", path: "x" },
      ]},
    ]},
  ],
};

const wait = (ms) => new Promise((r) => setTimeout(r, ms));
let cancelled = false;

const api = {
  async get_initial_state() {
    return {
      ok: true, appTitle: "Brightspace Downloader", version: "1.0.0",
      baseUrl: "", defaultDir: "C:\\Users\\you\\Documents\\Brightspace",
      fileManager: "File Explorer", existingPolicy: "skip", hasSavedSession: false,
      browserImport: { available: true, browsers: ["chrome", "edge", "firefox"] },
    };
  },
  async resume_session() { return { ok: false, error: "no session" }; },
  async set_base_url(url) {
    await wait(500);
    const host = url.replace(/^https?:\/\//, "").replace(/\/.*/, "") || "brightspace.tudelft.nl";
    return { ok: true, baseUrl: "https://" + host, host };
  },
  async login_with_window() {
    for (const m of ["Opening Brightspace…", "Signing in at login.tudelft.nl…", "Checking your Brightspace session…"]) {
      window.__bsdlEvent({ event: "login:status", payload: { message: m } });
      await wait(650);
    }
    return { ok: true, user: { name: "Robin Tester", uniqueName: "rtester" }, baseUrl: "https://brightspace.tudelft.nl" };
  },
  async pick_cookie_file() { await wait(300); return { ok: true, user: { name: "Robin Tester" } }; },
  async import_cookie_file() { return { ok: true, user: { name: "Robin Tester" } }; },
  async import_from_browser() { await wait(500); return { ok: true, user: { name: "Robin Tester" } }; },
  async logout() { return { ok: true }; },
  async list_courses() { await wait(400); return { ok: true, courses: COURSES, user: { name: "Robin Tester" } }; },
  async load_content(id) {
    await wait(500);
    if (id === 202) return { ok: true, fileCount: 0, nodes: [], skipped: {}, skippedText: "", defaultDir: TREE.defaultDir };
    return { ok: true, ...TREE };
  },
  async pick_folder(initial) { await wait(200); return { ok: true, path: initial || TREE.defaultDir }; },
  async start_download(ou, ids, dest, courseName, policy) {
    cancelled = false;
    const total = ids.length;
    const root = dest + "\\" + courseName;
    (async () => {
      const paths = [
        "Week 1/Reading Material - Copy.html", "Week 1/Lecture 1 - Introduction.pdf",
        "Week 1/Slides - Agility.pdf", "Week 1/Assignment 1 - Requirements/SEM_Assignment_1.pdf",
        "Week 2/Lecture 2.pdf", "Week 2/notes.pdf", "Week 2/notes (2).pdf",
      ];
      window.__bsdlEvent({ event: "download:start", payload: { total, dest: root } });
      let bytes = 0;
      for (let i = 0; i < total; i++) {
        if (cancelled) break;
        const fileTotal = 300000 + i * 120000;
        const name = paths[i % paths.length];
        for (let done = 0; done <= fileTotal; done += 90000) {
          if (cancelled) break;
          await wait(70);
          window.__bsdlEvent({ event: "download:progress", payload: {
            index: i + 1, total, name: name.split("/").pop(), path: "Software Engineering Methods (SEM)/" + name,
            fileBytes: Math.min(done, fileTotal), fileTotal, bytes: bytes + Math.min(done, fileTotal),
            totalBytes: null, fraction: (i + Math.min(done, fileTotal) / fileTotal) / total,
            speed: 1200000 + Math.random() * 400000,
          }});
        }
        bytes += fileTotal;
        if (i === 4 && !cancelled) {
          window.__bsdlEvent({ event: "download:error", payload: {
            path: "Software Engineering Methods (SEM)/" + paths[4], name: "Lecture 2.pdf",
            error: "HTTP 503 Service Unavailable",
          }});
        }
      }
      window.__bsdlEvent({ event: "download:done", payload: {
        total, downloaded: cancelled ? 2 : total - 1, skipped: 0,
        failed: cancelled ? [] : [{ path: "Software Engineering Methods (SEM)/" + paths[4], name: "Lecture 2.pdf", error: "HTTP 503 Service Unavailable" }],
        bytes, cancelled, abortedReason: "", notAttempted: cancelled ? total - 2 : 0, dest: root, seconds: 4.2,
      }});
    })();
    return { ok: true, count: total, dest: root };
  },
  async cancel_download() { cancelled = true; return { ok: true, cancelling: true }; },
  async reveal(path) { alert("Would open File Explorer at:\n" + path); return { ok: true }; },
};

window.pywebview = { api };
window.dispatchEvent(new Event("pywebviewready"));
