// Extract script bodies from trusted repository fixtures for syntax checks.
// This is a test helper, not an HTML sanitizer.
module.exports = function inlineScriptMatches(html) {
  return html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script\s*>/gi);
};
