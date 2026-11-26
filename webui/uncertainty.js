(function (root) {
  "use strict";

  function presentationFor(text) {
    const source = String(text ?? "");
    const normalized = source.toLocaleLowerCase();
    const refersToJapaneseText = /\b(japanese|kanji|hiragana|katakana)\b/.test(normalized);
    const refersToTranslation = /\b(meaning|semantic|translat\w*|interpret\w*)\b/.test(normalized);

    if (refersToJapaneseText && refersToTranslation) {
      return {
        title: "Translation needed to establish text meaning",
        text: source,
        guidance: "The exact semantic meaning of Japanese text cannot be established confidently without a translation. For a follow-up, start a new analysis, upload this design again, and add a translation or relevant context in Design brief.",
      };
    }

    if (/\b(audience|campaign|marketing)\b/.test(normalized)) {
      return {
        title: "Audience or campaign context needed",
        text: source,
        guidance: "Visual appearance alone cannot reliably establish the intended audience or campaign purpose. For a follow-up, start a new analysis, upload this design again, and add the audience or campaign goal in Design brief.",
      };
    }

    return {
      title: "Unresolved from the available evidence",
      text: source,
      guidance: "Review this point against the image and any supplied brief; the analysis does not assert a conclusion.",
    };
  }

  function mapToCards(items, createCard) {
    if (!Array.isArray(items)) return [];
    return items.map((text) => createCard(presentationFor(text)));
  }

  root.DemorphUncertainty = Object.freeze({ presentationFor, mapToCards });
  if (typeof module !== "undefined" && module.exports) {
    module.exports = root.DemorphUncertainty;
  }
})(globalThis);
