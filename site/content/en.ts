import { BROAD_LINE, COUNTEREXAMPLE, NARROW_LINE } from "./record";
import type { Dictionary } from "./types";

// Check names translate the ones in examples/acme/policy.json and the recorded proposals.
const checks = {
  web: "Users reach the web server over HTTPS",
  db: "Users reach the database on tcp/5432",
  internet: "The internet cannot reach the server network at all",
  ssh: "Users cannot SSH to the database server",
};

export const en: Dictionary = {
  lang: "en",
  otherLang: { label: "Türkçe", href: "/" },
  meta: {
    title: "NetLemma: verified network changes",
    description:
      "Claude writes the network change and Batfish formally verifies it before it goes live.",
  },
  og: {
    alt: "NetLemma: prove a network change before it goes live. In the example record, a narrow access-list line passes Batfish verification and is accepted.",
    label: "Example change record, round 2",
  },
  skipLink: "Skip to content",
  nav: { label: "Page sections", record: "Example record", how: "How it works", demo: "Demo", limits: "Limits" },
  labels: {
    eyebrow: "Verified network changes",
    process: "Process / 03 steps",
    fieldRepo: "Run it locally",
    fieldLive: "Real make demo output",
    fieldRequest: "Live walkthrough",
    scope: "Boundary of proof",
    chapter: "Chapter",
    availability: "Pilot access is open",
  },
  hero: {
    title: "Prove a network change before it goes live.",
    lede: "Describe the change in plain language. Claude writes the configuration change and Batfish verifies it against a model of your network. You only see changes that passed.",
    cta: "Request a demo",
    status: "Early prototype. Works today for Cisco IOS access lists.",
  },
  record: {
    label: "Example change record",
    title: "Example change record",
    provenance:
      "Real Batfish output with recorded proposals: both proposals were written by hand and recorded (--scripted); no model was called for this record.",
    requestLabel: "Change request",
    request: "Open tcp/5432 from the user network to the database server (10.20.20.30).",
    proved: "proved",
    violated: "violated",
    counterexample: "Counterexample",
    tablistLabel: "Verification rounds",
    diffLabel: "Change to the access list",
    rounds: [
      {
        tab: "Round 1",
        verdict: "Rejected",
        accepted: false,
        addedLine: BROAD_LINE,
        checks: [
          { label: checks.web, passed: true },
          { label: checks.internet, passed: true },
          { label: checks.ssh, passed: false, counterexample: COUNTEREXAMPLE },
          { label: checks.db, passed: true },
        ],
        stamp: "REJECTED",
      },
      {
        tab: "Round 2",
        verdict: "Accepted",
        accepted: true,
        addedLine: NARROW_LINE,
        checks: [
          { label: checks.web, passed: true },
          { label: checks.internet, passed: true },
          { label: checks.ssh, passed: true },
          { label: checks.db, passed: true },
        ],
        stamp: "ACCEPTED",
      },
    ],
  },
  how: {
    title: "How it works",
    steps: [
      {
        title: "Claude writes the change",
        body: "It reads your current configurations and rules, then writes a proposal that aims for the narrowest change meeting the request, plus flow checks meant to show the request is met.",
      },
      {
        title: "Batfish verifies it",
        body: "The change is applied to a model of the network. Each check is tested over the whole set of flows, not sample packets; anything that breaks comes back as a concrete counterexample.",
      },
      {
        title: "The counterexample goes back",
        body: "A rejected proposal goes back to Claude with the counterexample and a request to fix it, for up to three rounds. If nothing passes, your configuration is left untouched.",
      },
    ],
  },
  demo: {
    title: "Short demo",
    placeholder: "The demo recording is not ready yet.",
    body: "You can run the same flow on your own machine: the overly broad proposal is rejected with a counterexample and the narrow one is accepted. Docker and Python are enough; no API key needed.",
    commandLabel: "Command",
    setupLink: "Setup steps",
    requestBody: "We can also run the same flow for you live: the overly broad proposal is rejected with a counterexample and the narrow one is accepted.",
    requestLink: "Request a live walkthrough",
    videoNote:
      "The recording is real make demo output: Batfish is real, the two proposals are recorded (--scripted) and no model is called. Waiting and verification times are real time.",
    videoFallback: "The video could not be played in this browser (WebM format).",
    videoDownload: "Download the video",
  },
  proves: {
    title: "What it proves",
    items: [
      "That the proposal's own flow checks (intent checks) hold; each check is tested over the whole flow set it defines.",
      "That the change adds no new violation of your invariants and does not widen an existing one; violations that were already there are shown separately in the report.",
      "That the change adds no parse errors or undefined references.",
      "It also lists example flows whose behaviour changed, before and after.",
    ],
  },
  limits: {
    title: "What it does not",
    items: [
      "The intent checks are currently written by the model that proposes the change; that they cover the whole request is not separately proved.",
      "It cannot know a rule you never wrote down. Protection is only as strong as your invariants.",
      "Devices and features Batfish does not model are out of scope.",
      "The model is built from configuration; it does not see runtime problems such as hardware faults or software bugs.",
      "A person gives the final approval. The tool never pushes to a device itself.",
    ],
  },
  closing: {
    title: "Try it on your own network",
    body: "Verification runs in Batfish with no model call: on your own machine when run locally, in CI (a GitHub runner) for the PR bot. If you have Claude write the change (kanit plan, or /kanit plan on a PR), your configurations are sent to the Anthropic API. The tool never connects to a device. We are looking for our first pilot teams.",
    cta: "Write to us about a pilot",
    mailSubject: "contact",
  },
  footer: { builtOn: "Built on open-source", and: "and Claude.", source: "Source code" },
  notFound: {
    title: "Page not found",
    body: "The address you are looking for does not exist on this site.",
    home: "Go to the home page",
  },
};
