/* CaseHub App · JS canonical loader (no bundler — module-less)
 * Each <script src> is small + cached. Loaded in <head> with defer.
 */
(function () {
  'use strict';
  // Provide a single CSS-ready signal for early dark/light flash prevention
  document.documentElement.classList.add('ch-app-ready');
})();
