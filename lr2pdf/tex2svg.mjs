// Read a JSON array of {tex, display} from stdin, write a JSON array of SVG strings.
// LessWrong ships MathJax CHTML markup that needs MathJax's web fonts; re-rendering the
// original TeX to self-contained SVG paths gives print output with no font dependency.
import { mathjax } from 'mathjax-full/js/mathjax.js';
import { TeX } from 'mathjax-full/js/input/tex.js';
import { SVG } from 'mathjax-full/js/output/svg.js';
import { liteAdaptor } from 'mathjax-full/js/adaptors/liteAdaptor.js';
import { RegisterHTMLHandler } from 'mathjax-full/js/handlers/html.js';
import { AllPackages } from 'mathjax-full/js/input/tex/AllPackages.js';

const adaptor = liteAdaptor();
RegisterHTMLHandler(adaptor);
const doc = mathjax.document('', {
  InputJax: new TeX({ packages: AllPackages }),
  OutputJax: new SVG({ fontCache: 'none' }),
});

let input = '';
process.stdin.on('data', (d) => (input += d));
process.stdin.on('end', () => {
  const out = JSON.parse(input).map(({ tex, display }) => {
    try {
      const node = doc.convert(tex, { display, em: 16, ex: 8, containerWidth: 80 * 16 });
      return adaptor.innerHTML(node);
    } catch (e) {
      return null;
    }
  });
  process.stdout.write(JSON.stringify(out));
});
