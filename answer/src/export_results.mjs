import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {FileBlob, SpreadsheetFile} from '@oai/artifact-tool';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

export async function exportResult(question) {
  const cache = path.join(root, `answer/.cache/q${question}`);
  const results = path.join(root, 'answer/results');
  await fs.mkdir(cache, {recursive:true});
  await fs.mkdir(results, {recursive:true});
  const wb = await SpreadsheetFile.importXlsx(await FileBlob.load(path.join(root, `附件/附件2/result${question}.xlsx`)));
  const sheet = wb.worksheets.getItemAt(0);
  const lastCol = question === 3 ? 'C' : 'E';
  const previewOnly = process.argv.includes('--preview');
  let resultRows = [];
  if (!previewOnly) {
    const data = JSON.parse(await fs.readFile(path.join(cache, 'solution.json'), 'utf8'));
    resultRows = data.rows;
    if (data.rows.length) sheet.getRange(`A2:${lastCol}${data.rows.length + 1}`).values = data.rows;
    wb.recalculate();
    console.log((await wb.inspect({kind:'table', range:`${sheet.name}!A1:${lastCol}5`,
      include:'values,formulas', tableMaxRows:5, tableMaxCols:5, maxChars:1800})).ndjson);
    const scan = await wb.inspect({kind:'match', searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',
      options:{useRegex:true, maxResults:20}, summary:'Final formula error scan'});
    await fs.writeFile(path.join(cache, 'formula_scan.ndjson'), scan.ndjson);
  }
  const preview = await wb.render({sheetName:sheet.name, range:`A1:${lastCol}${previewOnly ? 5 : 16}`, scale:2, format:'png'});
  await fs.writeFile(path.join(cache, previewOnly ? 'template.png' : 'result.png'), new Uint8Array(await preview.arrayBuffer()));
  if (!previewOnly && question === 4) {
    const firstGap = resultRows.findIndex(row => row[3] !== null);
    if (firstGap >= 0) {
      const row = firstGap + 2;
      const detail = await wb.render({sheetName:sheet.name,
        range:`A${Math.max(1, row - 1)}:E${Math.min(resultRows.length + 1, row + 10)}`, scale:2, format:'png'});
      await fs.writeFile(path.join(cache, 'gap_adjustments.png'), new Uint8Array(await detail.arrayBuffer()));
    }
  }
  if (!previewOnly) {
    const output = path.join(results, `result${question}.xlsx`);
    await (await SpreadsheetFile.exportXlsx(wb)).save(output);
    try {
      await fs.rename(`${output}.inspect.ndjson`, path.join(cache, `result${question}.xlsx.inspect.ndjson`));
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
    }
    console.log(output);
  }
}
