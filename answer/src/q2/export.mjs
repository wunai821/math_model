import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {FileBlob, SpreadsheetFile} from '@oai/artifact-tool';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const cache=path.join(root,'answer/.cache/q2');
const results=path.join(root,'answer/results');
await fs.mkdir(cache,{recursive:true});
await fs.mkdir(results,{recursive:true});
const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(`${root}/附件/附件2/result2.xlsx`));
const sheet=wb.worksheets.getItemAt(0);
const previewOnly=process.argv.includes('--preview');
if (!previewOnly) {
  const data=JSON.parse(await fs.readFile(`${cache}/solution.json`,'utf8'));
  if(data.rows.length) sheet.getRange(`A2:D${data.rows.length+1}`).values=data.rows;
  wb.recalculate();
  console.log((await wb.inspect({kind:'table',range:`${sheet.name}!A1:D8`,include:'values,formulas',tableMaxRows:8,tableMaxCols:4})).ndjson);
}
const img=await wb.render({sheetName:sheet.name,range:previewOnly?'A1:D5':'A1:D16',scale:2,format:'png'});
await fs.writeFile(`${cache}/${previewOnly?'template':'result'}.png`,new Uint8Array(await img.arrayBuffer()));
if (!previewOnly) {
  await (await SpreadsheetFile.exportXlsx(wb)).save(`${results}/result2.xlsx`);
  try {
    await fs.rename(`${results}/result2.xlsx.inspect.ndjson`, `${cache}/result2.xlsx.inspect.ndjson`);
  } catch (error) {
    if(error.code !== 'ENOENT') throw error;
  }
}
