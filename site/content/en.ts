import { BROAD_LINE, COUNTEREXAMPLE, NARROW_LINE } from "./record";
import type { Dictionary } from "./types";

const checks = {
  db: "Users reach the database on tcp/5432",
  internet: "The internet cannot reach the server network",
  ssh: "Users cannot SSH to the database server",
};

export const en: Dictionary = {
  lang: "en",
  otherLang: { label: "Türkçe", href: "/" },
  meta: {
    title: "Kanıt: verified network changes",
    description:
      "Claude writes the network change and Batfish formally verifies it before it goes live.",
  },
  nav: { how: "How it works", limits: "Limits" },
  hero: {
    title: "Prove a network change before it goes live.",
    lede: "Describe the change in plain language. Claude writes the configuration change and Batfish verifies it against a model of your network. You only see changes that passed.",
    cta: "Request a demo",
    status: "Early prototype. Works today for Cisco IOS access lists.",
  },
  record: {
    label: "Example change record",
    requestLabel: "Change request",
    request: "Open tcp/5432 from the user network to the database server (10.20.20.30).",
    proved: "proved",
    violated: "violated",
    counterexample: "Counterexample",
    rounds: [
      {
        tab: "Round 1",
        verdict: "Rejected",
        accepted: false,
        addedLine: BROAD_LINE,
        checks: [
          { label: checks.db, passed: true },
          { label: checks.internet, passed: true },
          { label: checks.ssh, passed: false, counterexample: COUNTEREXAMPLE },
        ],
        stamp: "REJECTED",
      },
      {
        tab: "Round 2",
        verdict: "Accepted",
        accepted: true,
        addedLine: NARROW_LINE,
        checks: [
          { label: checks.db, passed: true },
          { label: checks.internet, passed: true },
          { label: checks.ssh, passed: true },
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
        body: "It reads your current configurations and rules, then produces the narrowest change that meets the request, plus the flow checks that would prove it.",
      },
      {
        title: "Batfish verifies it",
        body: "The change is applied to a model of the network. Each check is tested over the whole set of flows, not sample packets; anything that breaks comes back as a concrete counterexample.",
      },
      {
        title: "The counterexample goes back",
        body: "A rejected proposal is returned to Claude with the reason and gets fixed. If nothing passes, your configuration is left untouched.",
      },
    ],
  },
  proves: {
    title: "What it proves",
    items: [
      "That every flow the request requires is reachable, or blocked.",
      "That the invariant rules you defined still hold after the change.",
      "That the change adds no parse errors or undefined references.",
      "It also lists example flows whose behaviour changed, before and after.",
    ],
  },
  limits: {
    title: "What it does not",
    items: [
      "It cannot know a rule you never wrote down. Protection is only as strong as your invariants.",
      "Devices and features Batfish does not model are out of scope.",
      "The model is built from configuration; it does not see runtime problems such as hardware faults or software bugs.",
      "A person gives the final approval. The tool never pushes to a device itself.",
    ],
  },
  closing: {
    title: "Try it on your own network",
    body: "Your configurations stay with you: verification runs on a Batfish instance on your own machine. We are looking for our first pilot teams.",
    cta: "Write to us about a pilot",
  },
  footer: { builtOn: "Built on open-source", and: "and Claude.", source: "Source code" },
};
