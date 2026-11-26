const test = require("node:test");
const assert = require("node:assert/strict");
const { presentationFor, mapToCards } = require("./uncertainty.js");

test("Japanese text uncertainty explains the translation limit and next step", () => {
  const source = "Exact semantic meaning of Japanese text without translation";
  const item = presentationFor(source);

  assert.equal(item.text, source);
  assert.match(item.guidance, /exact semantic meaning.*cannot be established confidently without a translation/i);
  assert.match(item.guidance, /add a translation or relevant context in Design brief/i);
  assert.doesNotMatch(item.guidance, /Japanese means|translated as/i);
});

test("audience and campaign uncertainty requests a brief instead of inferring intent", () => {
  const source = "Intended audience or campaign purpose from visual alone";
  const item = presentationFor(source);

  assert.equal(item.text, source);
  assert.match(item.guidance, /visual appearance alone cannot reliably establish/i);
  assert.match(item.guidance, /add the audience or campaign goal in Design brief/i);
});

test("unrecognized uncertainty stays unresolved and retains the model text", () => {
  const source = "The intended role of the small mark is unclear";
  const item = presentationFor(source);

  assert.equal(item.title, "Unresolved from the available evidence");
  assert.equal(item.text, source);
  assert.match(item.guidance, /does not assert a conclusion/i);
});

test("multiple limitations produce one ordered presentation card per item", () => {
  const sources = [
    "Exact semantic meaning of Japanese text without translation",
    "Intended audience or campaign purpose from visual alone",
  ];
  const cards = mapToCards(sources, (item) => item);

  assert.equal(cards.length, 2);
  assert.equal(cards[0].text, sources[0]);
  assert.match(cards[0].title, /Translation/);
  assert.equal(cards[1].text, sources[1]);
  assert.match(cards[1].title, /Audience or campaign/);
});

test("non-list uncertainty data produces no cards", () => {
  assert.deepEqual(mapToCards(null, (item) => item), []);
});

test("result page loads the presenter before app code and maps cards into the existing section", () => {
  const fs = require("node:fs");
  const path = require("node:path");
  const html = fs.readFileSync(path.join(__dirname, "index.html"), "utf8");
  const app = fs.readFileSync(path.join(__dirname, "app.js"), "utf8");
  const presenterTag = html.indexOf('/assets/uncertainty.js');
  const appTag = html.indexOf('/assets/app.js');

  assert.ok(presenterTag >= 0 && appTag > presenterTag);
  assert.match(app, /DemorphUncertainty\.mapToCards\(result\.uncertainties/);
  assert.match(app, /Uncertainty & limitations/);
});
