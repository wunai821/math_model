import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {FileBlob, SpreadsheetFile} from '@oai/artifact-tool';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const cache=path.join(root,'answer/.cache/q1');
const results=path.join(root,'answer/results');
await fs.mkdir(cache,{recursive:true});
await fs.mkdir(results,{recursive:true});
const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(`${root}/附件/附件2/result1.xlsx`));
const sheet=wb.worksheets.getItemAt(0);
if(process.argv.includes('--preview')) {
 const img=await wb.render({sheetName:sheet.name,range:'A1:C5',scale:2,format:'png'});
 await fs.writeFile(`${cache}/template.png`,new Uint8Array(await img.arrayBuffer()));
} else {
 const data=JSON.parse(await fs.readFile(`${cache}/data.json`,'utf8'));
 sheet.getRange(`A2:C${data.pairs.length+1}`).values=data.pairs.map((p,i)=>[i+1,...p]);
 wb.recalculate();
 console.log((await wb.inspect({kind:'table',range:`${sheet.name}!A1:C8`,include:'values,formulas',tableMaxRows:8,tableMaxCols:3})).ndjson);
 const img=await wb.render({sheetName:sheet.name,range:'A1:C16',scale:2,format:'png'});
 await fs.writeFile(`${cache}/result.png`,new Uint8Array(await img.arrayBuffer()));
 await (await SpreadsheetFile.exportXlsx(wb)).save(`${results}/result1.xlsx`);
}
